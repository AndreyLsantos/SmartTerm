"""Offline regression tests. Run: python -m unittest -v test_smartterm.py"""
import asyncio
import contextlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from smartterm import (
    AIUnavailable, AIPredictor, App, Candidate, CommandHistory, CommandResult,
    ChatManager, FastPredictor, InvestigationContext, LlamaCppPredictor, ProjectIndex, SafetyClassifier,
    ShellExecutor, TerminalSanitizer, clean, ensure_tools_on_path, find_llama_server, gguf_name,
    WebResearcher, parse_args, redact, source_path, SYSTEM, argument_choices, catalog_search,
)

ensure_tools_on_path()


JAVA = '''package means;
public class ChatContent {
    public int mX;
    public byte type;
    public String strsContent;
    public String name;
}
'''
MENU = '''package face;
import means.ChatContent;
public class MenuUI {
    public void show(ChatContent chat) {
        if (chat.strsContent != null) {
            System.out.println(chat.strsContent);
        }
    }
    public ChatContent make() {
        return new ChatContent();
    }
}
'''


class Fixture:
    def setup_project(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.root = self.base / "projeto com espacos"
        self.root.mkdir()
        for name, content in {
            "Cliente/VN/src/means/ChatContent.java": JAVA,
            "Cliente/VN/src/face/MenuUI.java": MENU,
            "docs/PORT_STATUS.md": "ChatContent port: fields preserve null.\n",
            "node_modules/Hidden.java": "class Hidden {}",
            ".env": "password=not-for-the-model",
            "secret.key": "private-data",
            "Unity/Library/Cache.cs": "class Cache {}",
        }.items():
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        self.store = CommandHistory(self.base / "state/history.sqlite3")
        self.index = ProjectIndex(self.root, self.store)
        self.snapshot = self.index.build()

    def teardown_project(self):
        self.tmp.cleanup()


class IndexTests(Fixture, unittest.TestCase):
    def setUp(self):
        self.setup_project()

    def tearDown(self):
        self.teardown_project()

    def test_types_fields_methods_and_files(self):
        names = {s.name for s in self.snapshot.symbols}
        self.assertTrue({"ChatContent", "strsContent", "MenuUI", "show", "make"} <= names)
        self.assertEqual(len(self.snapshot.files), 3)

    def test_class_declaration_is_type_not_field(self):
        kinds = {(s.name, s.kind) for s in self.snapshot.symbols}
        self.assertIn(("ChatContent", "tipo"), kinds)
        self.assertNotIn(("ChatContent", "campo"), kinds)

    def test_secrets_and_generated_dirs_excluded(self):
        combined = "\n".join(self.snapshot.files)
        for name in (".env", "secret.key", "Hidden.java", "Cache.cs"):
            self.assertNotIn(name, combined)

    def test_no_symlink_escape(self):
        outside = self.base / "outside.java"
        outside.write_text("class External {}")
        link = self.root / "linked.java"
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest("Symlinks unavailable")
        self.assertIsNone(source_path(self.root, "linked.java"))
        self.assertIsNone(source_path(self.root, "../outside.java"))

    def test_retrieval_has_evidence_and_explicit_scope(self):
        report = self.index.retrieve("Quem usa ChatContent?")
        self.assertTrue(report.evidence)
        self.assertTrue(any("new ChatContent" in e.text for e in report.evidence))
        self.assertTrue(report.limited)
        self.assertGreater(report.searched_files, 0)
        self.assertTrue(all(e.line >= 1 for e in report.evidence))

    def test_retrieval_falls_back_to_python(self):
        with patch("smartterm.shutil.which", return_value=None):
            report = self.index.retrieve("ChatContent")
        self.assertEqual(report.engine, "python")
        self.assertTrue(report.evidence)

    def test_no_results_not_proof(self):
        report = self.index.retrieve("MissingClass")
        self.assertFalse(report.evidence)
        self.assertTrue(report.limited)
        self.assertIn("pode omitir", report.note)

    def test_incremental_cache(self):
        with patch.object(ProjectIndex, "parse_symbols", side_effect=AssertionError("Cache not used")):
            second = self.index.build()
        self.assertEqual(self.snapshot.symbols, second.symbols)
        target = self.root / "Cliente/VN/src/means/ChatContent.java"
        target.write_text(JAVA + "\nclass AddedType {}\n")
        third = self.index.build()
        self.assertIn("AddedType", {s.name for s in third.symbols})

    def test_deleted_file_pruned(self):
        (self.root / "docs/PORT_STATUS.md").unlink()
        after = self.index.build()
        self.assertNotIn("docs/PORT_STATUS.md", after.files)
        self.assertNotIn("docs/PORT_STATUS.md", self.store.cached_files(self.root))

    def test_local_ghost_symbol(self):
        fast = FastPredictor()
        fast.prepare(self.snapshot, self.root)
        c = fast.suggest('rg "Chat', [], [])
        self.assertIsNotNone(c)
        self.assertEqual(c.suffix, 'Content" Cliente/VN/src -g "*.java"')
        self.assertEqual(c.source, "indice")

    def test_new_instance_completion(self):
        fast = FastPredictor()
        fast.prepare(self.snapshot, self.root)
        self.assertEqual(fast.suggest('rg "new Chat', [], []).suffix, 'Content" Cliente/VN/src -g "*.java"')

    def test_history_has_priority(self):
        fast = FastPredictor()
        fast.prepare(self.snapshot, self.root)
        c = fast.suggest('rg "Chat', ['rg "ChatContent" Cliente/VN/src -g "*.java"'], [])
        self.assertEqual(c.source, "historico")
        self.assertTrue(c.suffix.endswith('"*.java"'))

    def test_fuzzy_only_menu(self):
        fast = FastPredictor()
        fast.prepare(self.snapshot, self.root)
        self.assertIsNone(fast.suggest('rg "Chta', [], []))
        self.assertTrue(any(c[0] == "ChatContent" for c in fast.menu('rg "ChtaConten')))

    def test_whole_command_templates_from_focus(self):
        fast = FastPredictor()
        fast.prepare(self.snapshot, self.root)
        options = fast.candidates("rg -n", [], ["ChatContent"], "powershell", True)
        fulls = [o.prefix + o.suffix for o in options]
        self.assertIn('rg -n -F "ChatContent" Cliente/VN/src -g "*.java"', fulls)
        self.assertIn('rg -n "new ChatContent\\b" Cliente/VN/src -g "*.java"', fulls)
        self.assertTrue(all(o.prefix == "rg -n" for o in options))

    def test_templates_complete_typed_symbol(self):
        fast = FastPredictor()
        fast.prepare(self.snapshot, self.root)
        c = fast.suggest("Get-ChildItem Cliente/VN/src -Recurse -Filter *.java | Select-String -SimpleMatch \"strs",
                         [], [], "powershell", False)
        self.assertEqual(c.suffix, 'Content"')

    def test_next_steps_after_search(self):
        fast = FastPredictor()
        fast.prepare(self.snapshot, self.root)
        ctx = InvestigationContext()
        ctx.add_record(CommandResult('rg -n -F "ChatContent"', str(self.root), "powershell",
                                     "Cliente/VN/src/face/MenuUI.java:10:        return new ChatContent();\n",
                                     0, .01), self.root)
        done = ['rg -n -F "ChatContent" Cliente/VN/src -g "*.java"']
        steps = [c.suffix for c in fast.next_steps(ctx, done, "powershell", True)]
        self.assertNotIn(done[0], steps)
        self.assertEqual(steps[0], 'rg -n -w "ChatContent" Cliente/VN/src -g "*.java"')
        self.assertIn('Get-Content "Cliente/VN/src/face/MenuUI.java" | Select-Object -Skip 0 -First 40', steps)

    def test_paths_relative_to_current_directory(self):
        fast = FastPredictor()
        fast.prepare(self.snapshot, self.root / "Cliente/VN/src")
        self.assertIn("means/ChatContent.java", fast.paths)

    def test_general_terminal_suggestions(self):
        fast = FastPredictor()
        fast.prepare(self.snapshot, self.root)
        ps = [c.prefix + c.suffix for c in fast.candidates("Get-Pro", [], [], "powershell")]
        cmd = [c.suffix for c in fast.next_steps(InvestigationContext(), [], "cmd")]
        bash = [c.prefix + c.suffix for c in fast.candidates("ls", [], [], "bash")]
        self.assertIn("Get-Process | Sort-Object CPU -Descending | Select-Object -First 10", ps)
        self.assertIn("dir", cmd)
        self.assertIn("ls -la", bash)

    def test_store_isolated_by_project_and_shell(self):
        result = CommandResult("rg ChatContent", str(self.root), "bash", "line", 0, .01)
        self.store.add(self.root, result)
        self.assertEqual(len(self.store.recent(self.root, "bash")), 1)
        self.assertFalse(self.store.recent(self.root, "powershell"))
        self.assertFalse(self.store.recent(self.base, "bash"))

    def test_sensitive_command_not_saved(self):
        result = CommandResult("echo password=abc123", str(self.root), "bash", "abc123", 0, .01)
        self.store.add(self.root, result)
        self.assertFalse(self.store.recent(self.root))

    def test_graph_records_text_associations_not_calls(self):
        ctx = InvestigationContext()
        ctx.add_record(CommandResult('rg -n "ChatContent"', str(self.root), "bash",
                                     "Cliente/VN/src/face/MenuUI.java:4:    public void show(ChatContent chat) {\n",
                                     0, .01), self.root)
        self.assertIn("ChatContent", ctx.entities)
        self.assertTrue(ctx.edges)
        self.assertEqual(ctx.edges[0]["kind"], "ocorrencia_textual")
        self.store.save_context(self.root, ctx.payload())
        recovered = InvestigationContext(self.store.load_context(self.root))
        self.assertEqual(recovered.entities, ctx.entities)


class SafetyTests(unittest.TestCase):
    def test_simple_search(self):
        self.assertEqual(SafetyClassifier.classify('rg -n -F "ChatContent" src -g "*.java"')[0], "SAFE")

    def test_dangerous_variants_not_whitelisted(self):
        commands = [
            "find . -delete", "find . -exec rm -rf {} +", "sed -i s/a/b/ file",
            "sed '1e touch pwned' file", "rg --pre evil pattern .", "rg --hostname-bin evil x",
            "git diff --ext-diff", "rm file", "Remove-Item -Recurse .", "echo x > f",
            "rg x; rm f", "rg x | bash", 'echo "$(rm f)"', "Get-ChildItem; Remove-Item x",
            "python script.py", "cmd /c del x", "rg x\nrm f",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(SafetyClassifier.classify(command)[0], "CONFIRM")

    def test_read_only_pipelines_and_quoted_regex(self):
        for command in ('Get-ChildItem -Recurse -Filter *.java | Select-String ChatContent',
                        'rg -n "show\\(|make\\(" src', 'rg -l Foo | sort',
                        'Get-Content "a b.java" | Select-Object -Skip 10 -First 40',
                        'Get-Process | Sort-Object CPU -Descending | Select-Object -First 10',
                        'Get-Service | Where-Object Status -EQ Running | Select-Object -First 20'):
            with self.subTest(command=command):
                self.assertEqual(SafetyClassifier.classify(command, "powershell")[0], "SAFE")
        for command in ("rg '--pre' evil x", "rg x | Remove-Item", "Get-ChildItem | ForEach-Object { rm $_ }",
                        "rg x || rm f", "sort -o out.txt in.txt", 'rg "a" > out.txt'):
            with self.subTest(command=command):
                self.assertEqual(SafetyClassifier.classify(command, "powershell")[0], "CONFIRM")

    def test_control_sequences_split_chunks(self):
        s = TerminalSanitizer()
        got = s.feed("a\x1b]52;c;") + s.feed("SECRET\x07b\x1b[31mred\x1b[0m\n")
        self.assertEqual(got, "abred\n")
        self.assertEqual(clean("\x1b[2Jhello"), "hello")


class CatalogTests(unittest.TestCase):
    def test_intent_search_per_shell(self):
        ps = [e.command for e in catalog_search("kill", "powershell")]
        self.assertIn("Stop-Process -Name ", ps)
        self.assertIn("taskkill /F /IM ", ps)
        self.assertEqual(catalog_search("kill", "bash")[0].command, "kill -9 ")
        self.assertTrue(all("taskkill" in e.command for e in catalog_search("matar processo", "cmd")))
        self.assertEqual(catalog_search("disco", "powershell")[0].command, "Get-PSDrive -PSProvider FileSystem")
        self.assertFalse(catalog_search('rg -n "x"', "powershell"))

    def test_live_arguments(self):
        procs = [("chrome.exe", "10|300 MB"), ("chrome.exe", "11|90 MB"), ("My App.exe", "12|5 MB")]
        svcs = [("Spooler", "rodando · Spooler"), ("wuauserv", "parado · Windows Update")]
        with patch.object(SYSTEM, "processes", return_value=procs), patch.object(SYSTEM, "services", return_value=svcs):
            start, items = argument_choices("taskkill /F /IM chr")
            self.assertEqual((start, items[0][0]), (-3, "chrome.exe"))
            self.assertIn("2 processos", items[0][2])
            _, items = argument_choices("Stop-Process -Id ")
            self.assertEqual([i[0] for i in items], ["10", "11", "12"])
            _, items = argument_choices("Stop-Service -Name ")
            self.assertEqual(items[0][0], "Spooler")
            _, items = argument_choices("net stop wua")
            self.assertEqual(items[0][0], "wuauserv")
            self.assertEqual(argument_choices("Stop-Service -N"), (0, []))
            if os.name == "nt":
                _, items = argument_choices("Stop-Process -Name my")
                self.assertEqual(items[0][0], '"My App"')


class PlannerTests(unittest.TestCase):
    def test_parse_planner_json_from_fence(self):
        got = ChatManager.parse_planner_json('```json\n{"action":"command","command":"dir"}\n```')
        self.assertEqual(got["command"], "dir")

    def test_clean_planned_command_rejects_multiline_and_internal(self):
        self.assertEqual(ChatManager.clean_planned_command("Get-ChildItem"), "Get-ChildItem")
        self.assertEqual(ChatManager.clean_planned_command("echo hi\nwhoami"), "")
        self.assertEqual(ChatManager.clean_planned_command("/exit"), "")

    def test_web_url_validation_blocks_local_networks_and_credentials(self):
        self.assertEqual(WebResearcher.normalize_url("www.example.com/a"), "https://www.example.com/a")
        for url in ("http://localhost/a", "http://127.0.0.1", "http://10.0.0.2",
                    "http://[::1]/", "https://user:secret@example.com"):
            with self.assertRaises(ValueError, msg=url):
                WebResearcher.normalize_url(url)

    def test_redaction(self):
        self.assertNotIn("super-secret", redact("api_key=super-secret\n"))
        self.assertNotIn("AAAA", redact("-----BEGIN PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----"))

    def test_suffix_rules(self):
        f = AIPredictor.suffix_from_response
        self.assertEqual(f('rg "Chat', 'Content" src -g "*.java"'), 'Content" src -g "*.java"')
        self.assertEqual(f('rg "Chat', 'rg "ChatContent"'), 'Content"')
        for bad in ('Content"; rm file', 'Content"\nrm file', '```bash', '<think>hello', 'Content" >x'):
            self.assertEqual(f('rg "Chat', bad), "")

    def test_powershell_uses_encoded_command(self):
        s = ShellExecutor("powershell", "pwsh")
        import base64
        args = s.argv('rg "ChatContent" "C:/pasta com espacos"')
        self.assertIn("-EncodedCommand", args)
        decoded = base64.b64decode(args[-1]).decode("utf-16le")
        self.assertIn('rg "ChatContent" "C:/pasta com espacos"', decoded)
        self.assertIn("LASTEXITCODE", decoded)


class AsyncTests(Fixture, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.setup_project()

    async def asyncTearDown(self):
        self.teardown_project()

    async def test_web_fetch_extracts_visible_text_only(self):
        async def handler(request):
            return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text=(
                "<html><head><title>Pagina teste</title><script>ignore()</script></head>"
                "<body><h1>Resultado atual</h1><p>Conteudo confirmado.</p></body></html>"
            ))
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        web = WebResearcher(client)
        try:
            with patch.object(WebResearcher, "ensure_public_url", new=AsyncMock(side_effect=lambda url: url)):
                source = await web.fetch("https://example.com/info")
            self.assertEqual(source.title, "Pagina teste")
            self.assertIn("Resultado atual", source.text)
            self.assertNotIn("ignore()", source.text)
        finally:
            await client.aclose()

    async def test_web_dns_private_address_is_blocked(self):
        answer = [(2, 1, 6, "", ("10.20.30.40", 0))]
        with patch("smartterm.socket.getaddrinfo", return_value=answer):
            with self.assertRaisesRegex(ValueError, "privada"):
                await WebResearcher.ensure_public_url("https://example.test/path")

    async def test_web_search_unwraps_duckduckgo_links(self):
        async def handler(request):
            body = ('<a class="result__a" href="//duckduckgo.com/l/?uddg='
                    'https%3A%2F%2Fexample.com%2Fnoticia">Exemplo atual</a>')
            return httpx.Response(200, headers={"content-type": "text/html"}, text=body)
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        web = WebResearcher(client)
        try:
            with patch.object(WebResearcher, "ensure_public_url", new=AsyncMock(side_effect=lambda url: url)):
                results = await web.search("exemplo")
            self.assertEqual(results, [("Exemplo atual", "https://example.com/noticia")])
        finally:
            await client.aclose()

    async def test_explicit_web_request_overrides_model_answer(self):
        with create_pipe_input() as inp:
            app = self.app(inp)
            async def fake_stream(messages):
                yield '{"action":"answer","answer":"nao sei"}'
            app.ai.stream_chat = fake_stream
            plan = await app.chat.plan_command("pesquise na internet a versao atual do Python")
            self.assertEqual(plan["action"], "web")
            self.assertIn("Python", plan["query"])
            self.assertFalse(app.chat.is_small_talk("qual a versao atual?"))
            async def malformed(messages):
                yield "nao-json"
            app.ai.stream_chat = malformed
            direct = await app.chat.plan_command("acesse https://example.com/docs e resuma")
            self.assertEqual(direct["action"], "web")
            self.assertEqual(direct["url"], "https://example.com/docs")
            await app.ai.close()

    async def test_bash_exec_real_search(self):
        if not shutil.which("bash") or not shutil.which("rg"):
            self.skipTest("bash/rg unavailable")
        r = await ShellExecutor("bash").run('rg -n "new ChatContent" Cliente/VN/src', self.root)
        self.assertEqual(r.exit_code, 0)
        self.assertIn("MenuUI.java:10:", r.output)

    async def test_bash_exit_code_one(self):
        if not shutil.which("bash") or not shutil.which("rg"):
            self.skipTest("bash/rg unavailable")
        r = await ShellExecutor("bash").run('rg MissingClass Cliente/VN/src', self.root)
        self.assertEqual(r.exit_code, 1)
        self.assertEqual(r.output, "")

    async def test_shell_cancellation(self):
        if not shutil.which("bash"):
            self.skipTest("bash unavailable")
        task = asyncio.create_task(ShellExecutor("bash").run("sleep 20", self.root))
        await asyncio.sleep(.1)
        task.cancel()
        result = await asyncio.wait_for(task, 3)
        self.assertEqual(result.exit_code, 130)

    async def test_output_bounded(self):
        if not shutil.which("bash"):
            self.skipTest("bash unavailable")
        cmd = "for ((i=0;i<2000;i++)); do echo '1234567890'; done"
        r = await ShellExecutor("bash").run(cmd, self.root)
        self.assertTrue(r.truncated)
        self.assertLess(len(r.output), 16100)

    async def test_powershell_plain_errors_and_exit_codes(self):
        exe = shutil.which("pwsh") or shutil.which("powershell")
        if not exe:
            self.skipTest("PowerShell unavailable")
        sh = ShellExecutor("powershell", exe)
        ok = await sh.run("Get-ChildItem -Recurse -Filter *.java | Select-String ChatContent", self.root)
        self.assertEqual(ok.exit_code, 0)
        self.assertIn("MenuUI.java", ok.output)
        self.assertNotIn("CLIXML", ok.output)
        missing = await sh.run("comando_que_nao_existe_xyz", self.root)
        self.assertEqual(missing.exit_code, 1)
        self.assertNotIn("CLIXML", missing.output)
        self.assertIn("comando_que_nao_existe_xyz", missing.output)

    async def test_chat_prints_whole_lines(self):
        async def handler(request):
            parts = ["Fa", "to: Chat", "Content e", " criado em\nMenu", "UI.java:10."]
            body = "\n".join(json.dumps({"message": {"content": p}, "done": False}) for p in parts)
            return httpx.Response(200, content=body + "\n" + json.dumps({"message": {"content": ""}, "done": True}))
        with create_pipe_input() as inp:
            app = self.app(inp)
            await app.ai.client.aclose()
            app.ai.client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=app.ai.url)
            printed = []
            with patch("builtins.print", side_effect=lambda *a, **k: printed.append(" ".join(map(str, a)))):
                await app.chat.ask("Onde ChatContent nasce?", app.project_version)
            lines = [p for p in printed if p.strip()]
            self.assertEqual(lines, ["IA> Fato: ChatContent e criado em", "    MenuUI.java:10."])
            await app.ai.close()

    async def test_ollama_mock_request_cache_and_think_false(self):
        requests = []
        async def handler(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200, json={"message": {"content": 'Content" src'}, "done": True})
        ai = AIPredictor("qwen3:4b", "http://127.0.0.1:11434")
        await ai.client.aclose()
        ai.client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=ai.url)
        ai.ready = True
        data = {"partial": 'rg "Chat', "cwd": str(self.root)}
        one = await ai.complete('rg "Chat', data)
        two = await ai.complete('rg "Chat', data)
        self.assertEqual(one, 'Content" src')
        self.assertEqual(one, two)
        self.assertEqual(len(requests), 1)
        self.assertIs(requests[0]["think"], False)
        self.assertEqual(requests[0]["options"]["num_predict"], 96)
        await ai.close()

    async def test_slow_model_timeout_keeps_local(self):
        async def handler(request):
            await asyncio.sleep(2)
            return httpx.Response(200, json={"message": {"content": "x"}})
        ai = AIPredictor("qwen3:4b", "http://127.0.0.1:11434", timeout=.05)
        await ai.client.aclose()
        ai.client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=ai.url)
        ai.ready = True
        self.assertEqual(await ai.complete("rg x", {"partial": "rg x"}), "")
        self.assertIn("limite", ai.last_error)
        await ai.close()

    async def test_offline_model_fails_soft(self):
        async def handler(request):
            raise httpx.ConnectError("offline", request=request)
        ai = AIPredictor("qwen3:4b", "http://127.0.0.1:11434")
        await ai.client.aclose()
        ai.client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=ai.url)
        await ai.warmup()
        self.assertFalse(ai.ready)
        self.assertEqual(await ai.complete("rg x", {}), "")
        await ai.close()

    async def test_chat_stream_uses_content_not_thinking(self):
        lines = [
            {"message": {"thinking": "not for UI", "content": "Fato: "}, "done": False},
            {"message": {"content": "ChatContent."}, "done": True},
        ]
        async def handler(request):
            return httpx.Response(200, content="\n".join(json.dumps(x) for x in lines))
        ai = AIPredictor("qwen3:4b", "http://127.0.0.1:11434")
        await ai.client.aclose()
        ai.client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=ai.url)
        output = "".join([c async for c in ai.stream_chat([{"role": "user", "content": "hello"}])])
        self.assertEqual(output, "Fato: ChatContent.")
        await ai.close()

    async def test_remote_endpoint_rejected(self):
        for url in ("https://example.com", "http://127.0.0.1.evil", "http://user:pw@localhost:11434"):
            with self.assertRaises(ValueError):
                AIPredictor("qwen3:4b", url)

    def app(self, inp):
        args = parse_args([str(self.root), "--shell", "bash", "--no-ai", "--ollama", "--state-dir", str(self.base / "appstate")])
        app = App(args, input=inp, output=DummyOutput())
        app.index = self.index
        app.fast.prepare(self.snapshot, self.root)
        return app

    async def start(self, app, capture=True):
        """Run the full-screen UI; optionally record submitted lines instead of executing them."""
        submitted = []
        if capture:
            async def fake(line):
                submitted.append(line)
            app.handle_line = fake
        task = asyncio.create_task(app.run())
        await asyncio.sleep(.15)
        return task, submitted

    async def stop(self, app, task):
        app.tui.exit()
        await asyncio.wait_for(task, 4)

    def log_text(self, app):
        return "\n".join("".join(t for _, t, *_ in line) for line in app.log.lines)

    async def test_typed_ghost_and_tab(self):
        with create_pipe_input() as inp:
            app = self.app(inp)
            task, submitted = await self.start(app)
            inp.send_text('rg "Chat')
            await asyncio.sleep(.08)
            self.assertIsNotNone(app.buffer.suggestion)
            self.assertEqual(app.buffer.suggestion.text, 'Content" Cliente/VN/src -g "*.java"')
            inp.send_text("\t\r")
            await asyncio.sleep(.08)
            self.assertEqual(submitted, ['rg "ChatContent" Cliente/VN/src -g "*.java"'])
            await self.stop(app, task)

    async def test_empty_prompt_is_clean_and_tab_lists(self):
        with create_pipe_input() as inp:
            app = self.app(inp)
            task, submitted = await self.start(app)
            self.assertIsNone(app.buffer.suggestion)
            inp.send_text("	")
            await asyncio.sleep(.2)
            state = app.buffer.complete_state
            self.assertTrue(state and state.completions)
            self.assertIn("ls -la", [c.text for c in state.completions])
            inp.send_text("")
            await asyncio.sleep(.1)
            inp.send_text("kill")
            await asyncio.sleep(.2)
            state = app.buffer.complete_state
            self.assertIn("pkill ", [c.text for c in state.completions])
            await self.stop(app, task)

    async def test_enter_does_not_accept_ghost(self):
        with create_pipe_input() as inp:
            app = self.app(inp)
            task, submitted = await self.start(app)
            inp.send_text('rg "Chat')
            await asyncio.sleep(.05)
            inp.send_text("\r")
            await asyncio.sleep(.08)
            self.assertEqual(submitted, ['rg "Chat'])
            await self.stop(app, task)

    async def test_stale_model_suggestion_ignored(self):
        with create_pipe_input() as inp:
            app = self.app(inp)
            app.args.debounce_ms = 50
            app.ai_enabled = True
            app.ai.ready = True
            async def slow(partial, data):
                # Emulate an uncooperative server; client must still check generation.
                try:
                    await asyncio.sleep(.2)
                except asyncio.CancelledError:
                    pass
                return "OLD_RESULT"
            app.ai.complete = slow
            app.start_warmup = lambda: None
            task, submitted = await self.start(app)
            inp.send_text('rg "Chat')
            await asyncio.sleep(.08)
            inp.send_text("Content")
            await asyncio.sleep(.08)
            suggestion = app.buffer.suggestion
            self.assertTrue(suggestion is None or suggestion.text != "OLD_RESULT")
            inp.send_text("\r")
            await asyncio.sleep(.08)
            self.assertEqual(submitted, ['rg "ChatContent'])
            await self.stop(app, task)

    async def test_cwd_and_context_switch(self):
        with create_pipe_input() as inp:
            app = self.app(inp)
            with patch("builtins.print"):
                await app.set_cwd("Cliente/VN/src")
            self.assertEqual(app.cwd, self.root / "Cliente/VN/src")
            self.assertIn("means/ChatContent.java", app.fast.paths)
            with self.assertRaises(ValueError):
                await app.set_cwd(str(self.base))
            await app.ai.close()

    async def test_why_not_overwritten_by_internal_commands(self):
        with create_pipe_input() as inp:
            app = self.app(inp)
            task, submitted = await self.start(app)
            inp.send_text('rg "Chat')
            await asyncio.sleep(.05)
            self.assertEqual(app.last_suggestion.source, "indice")
            inp.send_text("\x15/why")
            await asyncio.sleep(.05)
            self.assertEqual(app.last_suggestion.source, "indice")
            await self.stop(app, task)

    async def test_history_does_not_offer_wrong_cwd(self):
        with create_pipe_input() as inp:
            app = self.app(inp)
            app.history_rows = [{"cwd": str(self.root), "command": "rg ChatContent Cliente/VN/src"}]
            app.cwd = self.root / "Cliente/VN/src"
            app.refresh_history_memory()
            self.assertFalse(app.history_lines)
            await app.ai.close()

    async def test_chat_context_contains_null_evidence(self):
        with create_pipe_input() as inp:
            app = self.app(inp)
            app.context.touch_entity("ChatContent")
            app.context.add_retrieval(self.index.retrieve("ChatContent strsContent"))
            messages = app.chat.messages("Posso iniciar as strings com string.Empty?")
            self.assertIn("strsContent != null", messages[-1]["content"])
            self.assertIn("MenuUI.java", messages[-1]["content"])
            self.assertIn("ChatContent", messages[-1]["content"])
            self.assertLess(sum(len(m["content"]) for m in messages[1:]), app.args.context_chars + 200)
            # The question is the last thing the model reads.
            self.assertTrue(messages[-1]["content"].rstrip().endswith("Posso iniciar as strings com string.Empty?"))
            await app.ai.close()

    async def test_small_talk_gets_no_old_search_data(self):
        with create_pipe_input() as inp:
            app = self.app(inp)
            app.context.touch_entity("ChatContent")
            app.context.add_retrieval(self.index.retrieve("ChatContent"))
            for greeting in ("ola", "tudo bem?", "o que voce faz?", "bom dia"):
                self.assertTrue(app.chat.is_small_talk(greeting), greeting)
            for work in ("onde ChatContent e criado?", "explique o ultimo comando", "o que falta verificar?",
                         "quem usa strsContent", "e esse erro?"):
                self.assertFalse(app.chat.is_small_talk(work), work)
            text = app.chat.messages("ola", small_talk=True)[-1]["content"]
            self.assertNotIn("MenuUI.java", text)
            self.assertEqual(text, "ola")
            await app.ai.close()

    async def test_cli_whole_session_local(self):
        with create_pipe_input() as inp:
            app = self.app(inp)
            task, _ = await self.start(app, capture=False)
            inp.send_text("/project\r")
            await asyncio.sleep(.2)
            inp.send_text("rg -n -F ChatContent Cliente/VN/src\r")
            for _ in range(40):
                await asyncio.sleep(.1)
                if "exit=" in self.log_text(app) and not app.busy:
                    break
            inp.send_text("/context\r")
            await asyncio.sleep(.2)
            inp.send_text("/exit\r")
            await asyncio.wait_for(task, 4)
            history = app.store.recent(app.root)
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["exit_code"], 0)
            self.assertIn("ChatContent", app.context.entities)
            text = self.log_text(app)
            self.assertIn("MenuUI.java:10:", text)
            self.assertIn("› rg -n -F ChatContent Cliente/VN/src", text)

    async def test_llamacpp_openai_stream_and_complete(self):
        async def handler(request):
            body = json.loads(request.content)
            self.assertEqual(request.url.path, "/v1/chat/completions")
            if body.get("stream"):
                chunks = [{"choices": [{"delta": {"content": p}, "finish_reason": None}]} for p in ("Fa", "to.")]
                sse = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
                return httpx.Response(200, content=sse)
            return httpx.Response(200, json={"choices": [{"message": {"content": 'Content" src'}}]})
        ai = LlamaCppPredictor(None, None, 2.5, 4096, 0, self.base / "llama.log")
        self.assertIn("sem modelo", ai.status)
        await ai.client.aclose()
        ai.client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://127.0.0.1:1")
        ai.ready = True
        self.assertEqual(await ai.complete('rg "Chat', {"partial": 'rg "Chat'}), 'Content" src')
        self.assertEqual("".join([c async for c in ai.stream_chat([{"role": "user", "content": "x"}])]), "Fato.")
        await ai.close()

    async def test_llamacpp_real_server(self):
        model = os.environ.get("SMARTTERM_TEST_GGUF")
        if not model or not find_llama_server():
            self.skipTest("defina SMARTTERM_TEST_GGUF e tenha llama\\llama-server.exe")
        ai = LlamaCppPredictor(model, find_llama_server(), 5, 4096, -1, self.base / "llama.log")
        self.assertNotEqual(gguf_name(Path(model)), "")
        await ai.warmup()
        try:
            self.assertTrue(ai.ready, ai.last_error)
            answer = "".join([c async for c in ai.stream_chat([{"role": "user", "content": "Responda apenas: ok"}])])
            self.assertTrue(answer.strip())
        finally:
            await ai.close()
        self.assertIsNone(ai.server)

    async def test_intellisense_popup(self):
        from prompt_toolkit.completion import CompleteEvent
        from prompt_toolkit.document import Document
        with create_pipe_input() as inp:
            app = self.app(inp)
            app.context.touch_entity("ChatContent")
            comp = app.buffer.completer.completer
            def items(text):
                return [(c.text, c.display_meta_text) for c in comp.get_completions(Document(text), CompleteEvent())]
            names = [t for t, _ in items("gr")]
            self.assertIn("grep ", names)
            flags = dict(items("grep -"))
            self.assertIn("-r ", flags)
            self.assertEqual(flags["-r "], "recursivo")
            whole = [t for t, _ in items("rg -n")]
            self.assertIn('rg -n -F "ChatContent" Cliente/VN/src -g "*.java"', whole)
            ps = dict(items("Get-ChildItem -R"))
            self.assertIn("-Recurse ", ps)
            await app.ai.close()

    async def test_select_copy_and_paste(self):
        from smartterm import Clipboard
        with create_pipe_input() as inp:
            app = self.app(inp)
            app.log.write("Cliente/VN/src/face/MenuUI.java:10: return new ChatContent();\nsegunda linha\n")
            app.log.select(0, 0, start=True)
            app.log.select(0, 30, start=False)
            self.assertEqual(app.log.selected_text(), "Cliente/VN/src/face/MenuUI.java")
            app.log.select(1, 6, start=False)
            self.assertTrue(app.log.selected_text().endswith("\nsegunda"))
            with patch.object(Clipboard, "set", return_value=True) as copied:
                task, _ = await self.start(app)
                inp.send_text("\x03")  # Ctrl+C with a selection copies instead of interrupting
                await asyncio.sleep(.1)
                self.assertTrue(copied.called)
                self.assertIsNone(app.log.span())
                with patch.object(Clipboard, "get", return_value="rg -n\r\n\"ChatContent\"\r\n"):
                    inp.send_text("\x16")  # Ctrl+V
                    await asyncio.sleep(.1)
                self.assertEqual(app.buffer.text, 'rg -n "ChatContent"')
                await self.stop(app, task)

    def test_windows_clipboard_roundtrip(self):
        from smartterm import Clipboard
        if os.name != "nt":
            self.skipTest("Windows only")
        original = Clipboard.get()
        try:
            self.assertTrue(Clipboard.set("SmartTerm ção\nlinha 2"))
            self.assertEqual(Clipboard.get(), "SmartTerm ção\r\nlinha 2")
        finally:
            Clipboard.set(original)  # give the user's clipboard back

    async def test_confirmation_in_input_box(self):
        with create_pipe_input() as inp:
            app = self.app(inp)
            task, _ = await self.start(app, capture=False)
            inp.send_text("rm -rf nada\r")
            await asyncio.sleep(.2)
            self.assertIsNotNone(app.pending_confirm)
            inp.send_text("n\r")
            await asyncio.sleep(.2)
            self.assertIsNone(app.pending_confirm)
            self.assertIn("Cancelado", self.log_text(app))
            self.assertFalse(app.store.recent(app.root))
            await self.stop(app, task)

    async def test_conversation_scrolls_and_clears(self):
        with create_pipe_input() as inp:
            app = self.app(inp)
            with contextlib.redirect_stdout(app.log):
                for i in range(50):
                    print(f"linha {i}")
            app.log.scroll(10)
            self.assertEqual(app.log.offset, 10)
            print_line = len(app.log.lines)
            app.log.write("nova\n")
            self.assertEqual(app.log.offset, 11)  # view stays on the same text
            self.assertEqual(len(app.log.lines), print_line + 1)
            app.log.clear()
            self.assertFalse(app.log.lines)
            await app.ai.close()

    async def test_scroll_moves_view_from_first_step(self):
        # Regression: the view stood still until the offset exceeded the window height.
        from prompt_toolkit.application import Application
        from prompt_toolkit.application.current import set_app
        from prompt_toolkit.layout import Window
        from prompt_toolkit.layout.controls import FormattedTextControl
        from prompt_toolkit.layout.mouse_handlers import MouseHandlers
        from prompt_toolkit.layout.screen import Screen, WritePosition
        from smartterm import ConversationLog
        log = ConversationLog()
        for i in range(100):
            log.write(f"linha {i}\n")
        window = Window(FormattedTextControl(lambda: log.fragments(None)), wrap_lines=True)
        with create_pipe_input() as inp:
            tui = Application(input=inp, output=DummyOutput())
            with set_app(tui):
                for offset in (0, 1, 5, 30, 0):
                    log.scroll(offset - log.offset)
                    tui.render_counter += 1
                    screen = Screen()
                    window.write_to_screen(screen, MouseHandlers(), WritePosition(0, 0, 20, 10), "", False, None)
                    rows = ["".join(screen.data_buffer[y][x].char for x in range(20)).strip() for y in range(10)]
                    self.assertEqual([r for r in rows if r][-1], f"linha {99 - offset}")

    async def test_planner_gets_tested_commands_and_approval_is_not_repeated(self):
        with create_pipe_input() as inp:
            app = self.app(inp)
            app.shell = ShellExecutor("powershell", "powershell")
            data = json.loads(app.chat.planner_messages("quanto de espaço tem meu disco local C")[-1]["content"])
            self.assertEqual(data["known_commands"][0]["command"], "Get-PSDrive -PSProvider FileSystem")
            app.shell.run = AsyncMock(return_value=CommandResult("x", str(self.root), "powershell", "", 0, .01))
            app.confirm = AsyncMock(return_value=False)
            with patch("builtins.print"):
                await app.execute("Get-PSDrive | Where-Object {$_.Name -eq 'C'}", approved=True)
            app.confirm.assert_not_called()
            self.assertTrue(app.shell.run.called)
            await app.ai.close()

    async def test_search_engine_url_becomes_search_and_news_uses_rss(self):
        calls = []
        rss = ("<rss><channel><item><title>One Piece entra em hiato - Site</title>"
               "<pubDate>Mon, 28 Sep 2026 20:00:00 GMT</pubDate></item>"
               "<item><title>One Piece entra em hiato - Site</title></item></channel></rss>")
        async def handler(request):
            calls.append(str(request.url))
            if request.url.host == "news.google.com":
                return httpx.Response(200, text=rss, headers={"content-type": "application/xml"})
            return httpx.Response(200, text="<html><body></body></html>", headers={"content-type": "text/html"})
        web = WebResearcher(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        with patch.object(WebResearcher, "ensure_public_url", AsyncMock(side_effect=lambda u: u)):
            sources = await web.research(url="https://www.google.com/search?q=ultimas+noticias+One+Piece", news=True)
        self.assertFalse(any("google.com/search" in c for c in calls))
        self.assertIn("q=One+Piece", calls[0])  # filler words dropped from the news topic
        self.assertEqual(sources[0].text, "2026-09-28 | One Piece entra em hiato - Site")  # deduplicated
        await web.client.aclose()

    async def test_session_module(self):
        from smartterm import KnowledgeModule
        material = self.base / "sqli.txt"
        material.write_text("# SQL Injection\n\nDados concatenados na consulta SQL.\n\n## Prevencao\n\n"
                            "Use consultas parametrizadas (prepared statements).\n", encoding="cp1252")
        with create_pipe_input() as inp:
            app = self.app(inp)
            with patch("builtins.print"):
                await app.internal(f"/modulo {material}")
            self.assertIsInstance(app.module, KnowledgeModule)
            self.assertTrue(app.chat.uses_module("como prevenir sql injection?"))
            self.assertTrue(app.chat.uses_module("liste as formas de prevencao de sql injection"))
            self.assertFalse(app.chat.uses_module("liste os processos abertos"))  # command, not material
            self.assertFalse(app.chat.uses_module("pesquise na internet sobre sql injection"))
            messages, where = app.chat.module_messages("como prevenir?", app.module)
            self.assertIn("parametrizadas", messages[-1]["content"])
            self.assertTrue(messages[-1]["content"].rstrip().endswith("como prevenir?"))
            self.assertEqual(where, ["[1] sqli.txt:1-7"])
            with patch("builtins.print"):
                await app.internal("/modulo off")
            self.assertIsNone(app.module)
            with self.assertRaises(ValueError):
                await app.internal(f"/modulo {self.base / 'nada.txt'}")
            await app.ai.close()

    async def test_context_clear_keeps_command_history(self):
        with create_pipe_input() as inp:
            app = self.app(inp)
            r = CommandResult("rg ChatContent", str(self.root), "bash", "", 1, .1)
            app.store.add(self.root, r)
            app.context.add_record(r, self.root)
            with patch("builtins.print"):
                await app.internal("/clear-context")
            self.assertFalse(app.context.records)
            self.assertEqual(len(app.store.recent(self.root)), 1)
            await app.ai.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)

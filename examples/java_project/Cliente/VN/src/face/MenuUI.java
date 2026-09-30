// Minimal synthetic search example. Not a real game screen.
package face;

import means.ChatContent;
import model.CollectionObject;

public class MenuUI {
    public ChatContent createChat() {
        return new ChatContent();
    }

    public void showChat(ChatContent chat) {
        if (chat.strsContent != null) {
            System.out.println(chat.strsContent);
        }
    }

    private void drawCollectionOption(CollectionObject item) {
        System.out.println(item.shtIcon);
    }
}

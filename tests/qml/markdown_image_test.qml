import QtQuick
import "chatEvents.js" as CE

// Renders Markdown with three image forms pointing at a local port, so the
// test can count how many requests Qt actually makes.
Window {
  visible: true; width: 400; height: 300
  property string raw: "inline ![a](http://127.0.0.1:__PORT__/inline.png)\n\nref ![b][r]\n\n[r]: http://127.0.0.1:__PORT__/ref.png"
  Text {
    width: 400
    wrapMode: Text.WordWrap
    textFormat: Text.MarkdownText
    text: __TEXT_EXPR__
  }
  Timer { interval: 1500; running: true; onTriggered: Qt.exit(0) }
}

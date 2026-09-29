import QtQuick
import "chatEvents.js" as CE

// Runs headless under qml6. Prints ALL PASSED and exits 0, or lists failures.
Window {
  visible: true; width: 10; height: 10
  property int failures: 0

  function check(name, ok) {
    if (!ok) { failures++; console.log("FAIL: " + name) }
  }

  function same(a, b) { return JSON.stringify(a) === JSON.stringify(b) }

  function runChecks() {
    // parseLine: only well-formed events with a string type get through
    check("parse valid", same(CE.parseLine('{"type":"token","text":"hi"}'), {type: "token", text: "hi"}))
    check("parse tolerates surrounding whitespace", CE.parseLine('  {"type":"done"}\r\n').type === "done")
    check("parse blank -> null", CE.parseLine("") === null && CE.parseLine("   ") === null)
    check("parse garbage -> null", CE.parseLine("not json") === null)
    check("parse truncated json -> null", CE.parseLine('{"type":"tok') === null)
    check("parse json without type -> null", CE.parseLine('{"text":"x"}') === null)
    check("parse non-string type -> null", CE.parseLine('{"type":5}') === null)
    check("parse json null -> null", CE.parseLine("null") === null)
    check("parse json number -> null", CE.parseLine("123") === null)
    check("parse json array -> null", CE.parseLine("[1,2]") === null)

    // interpret
    check("tool -> status", same(CE.interpret({type: "tool", name: "system_control"}), {status: "running system_control…"}))
    check("token keeps leading space", CE.interpret({type: "token", text: " that"}).text === " that")
    check("token clears status", CE.interpret({type: "token", text: "x"}).status === "")
    check("token newline preserved", CE.interpret({type: "token", text: "a\n- b"}).text === "a\n- b")
    check("done", same(CE.interpret({type: "done"}), {done: true}))
    check("error", same(CE.interpret({type: "error", message: "boom"}), {done: true, failed: true, text: "boom"}))
    check("unknown type -> null", CE.interpret({type: "future-thing"}) === null)

    // abnormalExit: silence when the server finished properly, a reason otherwise
    check("clean finish, exit 0", CE.abnormalExit(0, true) === "")
    check("terminal seen beats a bad exit code", CE.abnormalExit(18, true) === "")
    check("exit 7 = cannot reach", CE.abnormalExit(7, false).indexOf("reach") >= 0)
    check("exit 28 = too long", CE.abnormalExit(28, false).indexOf("too long") >= 0)
    check("exit 18 = dropped", CE.abnormalExit(18, false).indexOf("dropped") >= 0)
    check("exit 0 without terminal = hung up", CE.abnormalExit(0, false).indexOf("hung up") >= 0)

    // streamCommand: argv array, correct url, body round-trips any message
    var cmd = CE.streamCommand("http://h:9/", "t1", "hello", 30)
    check("argv starts with curl -sN", cmd[0] === "curl" && cmd[1] === "-sN")
    check("timeout is a string arg", cmd[cmd.indexOf("--max-time") + 1] === "30")
    check("trailing slash trimmed", cmd.indexOf("http://h:9/chat/stream") >= 0)
    check("many trailing slashes trimmed", CE.streamCommand("http://h:9///", "t", "m", 5).indexOf("http://h:9/chat/stream") >= 0)
    var nasty = 'say "hi"; $(rm -rf ~) `id` \n newline \u{1F389} \\'
    var body = JSON.parse(CE.streamCommand("http://h", "t", nasty, 5).slice(-1)[0])
    check("nasty message round-trips verbatim", body.message === nasty)
    check("thread id sent", body.thread_id === "t")
    check("message never appears as its own argv element",
          CE.streamCommand("http://h", "t", "rm -rf /", 5).indexOf("rm -rf /") === -1)

    // newSessionId: a fresh, URL-safe conversation id under the configured base
    check("session id is base-timestamp", CE.newSessionId("bar", 1790000000000) === "bar-1790000000000")
    check("session ids differ over time", CE.newSessionId("bar", 1) !== CE.newSessionId("bar", 2))
    check("a trailing dash in the base is not doubled", CE.newSessionId("bar-", 5) === "bar-5")
    check("empty base gets a default", CE.newSessionId("", 5) === "session-5")
    check("junk-only base gets a default", CE.newSessionId("!!!", 5) === "session-5")
    check("unsafe characters become one dash", CE.newSessionId("my thread!", 5) === "my-thread-5")
    check("numeric-string time works", CE.newSessionId("bar", "7") === "bar-7")
    check("id has only URL-safe characters", /^[A-Za-z0-9_-]+$/.test(CE.newSessionId("a b/c?d", 9)))

    // parseCommand: /commands typed into the input; anything else is a normal message
    check("/new", same(CE.parseCommand("/new"), {name: "new", arg: "", known: true}))
    check("surrounding spaces ignored", CE.parseCommand("  /history  ").name === "history")
    check("argument is kept", CE.parseCommand("/open 3").arg === "3")
    check("command names are case-insensitive", CE.parseCommand("/OPEN 3").name === "open")
    check("multi-word argument", CE.parseCommand("/help me please").arg === "me please")
    check("plain text is not a command", CE.parseCommand("hello") === null)
    check("empty is not a command", CE.parseCommand("") === null)
    check("lone slash is not a command", CE.parseCommand("/") === null)
    check("a path is a message, not a command", CE.parseCommand("/etc/hosts show me") === null)
    check("space after the slash is a message", CE.parseCommand("/ new") === null)
    check("digits break the command shape", CE.parseCommand("/new2") === null)
    check("slash mid-sentence is a message", CE.parseCommand("hello /new") === null)
    check("unknown command-shaped word is flagged", CE.parseCommand("/histroy").known === false)
    check("every real command is known",
          ["new", "history", "open", "help"].every(function(n) { return CE.parseCommand("/" + n).known }))
    check("/more is not a command any more (the Show more button does that)", CE.parseCommand("/more").known === false)

    // URLs and the request for reading history
    check("history url fetches one extra row to learn if there is more",
          CE.historyUrl("http://h:9/", "bar", 10) === "http://h:9/threads?prefix=bar&limit=11")
    check("prefix is url-encoded", CE.historyUrl("http://h", "a b", 10).indexOf("prefix=a%20b") >= 0)
    check("limit is capped at the server maximum of 100", CE.historyUrl("http://h", "bar", 99).indexOf("limit=100") >= 0
          && CE.historyUrl("http://h", "bar", 500).indexOf("limit=100") >= 0)
    check("messages url", CE.messagesUrl("http://h/", "bar-1") === "http://h/threads/bar-1/messages")
    check("thread id is url-encoded in the path", CE.messagesUrl("http://h", "a/b") === "http://h/threads/a%2Fb/messages")
    check("GET command is an argument array", same(CE.getCommand("http://h/x", 20), ["curl", "-s", "--max-time", "20", "http://h/x"]))

    // reading server answers
    check("json list parses", same(CE.parseJsonList('[{"a":1}]'), [{a: 1}]))
    check("empty list parses", same(CE.parseJsonList("[]"), []))
    check("an error object is not a list", CE.parseJsonList('{"detail":"no such thread"}') === null)
    check("garbage is not a list", CE.parseJsonList("not json") === null && CE.parseJsonList("") === null)

    // paging: first page, then Load more
    var eleven = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
    check("more rows than the page -> show page, offer Load more", CE.pageOf(eleven, 10).rows.length === 10 && CE.pageOf(eleven, 10).hasMore === true)
    check("exactly a page -> no Load more", CE.pageOf(eleven.slice(0, 10), 10).hasMore === false)
    check("fewer than a page -> no Load more", CE.pageOf([1, 2, 3], 10).hasMore === false && CE.pageOf([1, 2, 3], 10).rows.length === 3)
    check("empty and invalid input give an empty page", same(CE.pageOf([], 10), {rows: [], hasMore: false}) && same(CE.pageOf(null, 10), {rows: [], hasMore: false}))

    // time-ago labels
    var now = Date.parse("2026-09-29T12:00:00Z")
    var ago = function(ms) { return new Date(now - ms).toISOString() }
    check("30 s ago", CE.relativeTime(ago(30000), now) === "just now")
    check("59 min ago", CE.relativeTime(ago(59 * 60000), now) === "59 min ago")
    check("60 min ago is 1 h", CE.relativeTime(ago(60 * 60000), now) === "1 h ago")
    check("2 h ago", CE.relativeTime(ago(2 * 3600000), now) === "2 h ago")
    check("30 h ago is yesterday", CE.relativeTime(ago(30 * 3600000), now) === "yesterday")
    check("5 days ago is a short date", /^[A-Z][a-z]{2} \d{1,2}$/.test(CE.relativeTime(ago(5 * 86400000), now)))
    check("a timestamp slightly in the future is just now", CE.relativeTime(ago(-600000), now) === "just now")
    check("garbage timestamp gives empty text", CE.relativeTime("garbage", now) === "")

    check("a real server timestamp (microseconds, +00:00) parses",
          CE.relativeTime("2026-09-29T09:25:11.215055+00:00", Date.parse("2026-09-29T11:25:12Z")) === "2 h ago")

    // one row of the history list
    var row = {thread_id: "bar-1", title: "hello", updated_at: ago(2 * 3600000), message_count: 56}
    check("session row", same(CE.describeSession(row, 1, now), {number: 1, title: "hello", meta: "56 msgs · 2 h ago", threadId: "bar-1"}))
    check("singular message", CE.describeSession({thread_id: "x", title: "t", updated_at: ago(1000), message_count: 1}, 2, now).meta.indexOf("1 msg ·") === 0)
    var longRow = {thread_id: "x", title: "z".repeat(60), updated_at: ago(1000), message_count: 2}
    check("long title is shortened for the list", CE.describeSession(longRow, 1, now).title.length === 34 && CE.describeSession(longRow, 1, now).title.slice(-1) === "…")

    // /open <number>
    check("open 3", CE.openIndex("3", 10) === 3)
    check("open tolerates spaces", CE.openIndex(" 2 ", 10) === 2)
    check("open rejects zero, negatives, beyond the list, words, decimals, empty",
          [CE.openIndex("0", 10), CE.openIndex("-1", 10), CE.openIndex("11", 10), CE.openIndex("x", 10), CE.openIndex("2.5", 10), CE.openIndex("", 10)].every(function(v) { return v === null }))
    check("open with an empty list is refused", CE.openIndex("1", 0) === null)

    // messages loaded from the server become chat rows
    var loaded = CE.messagesFromServer([{role: "you", text: "hi"}, {role: "kokki", text: "yo"}])
    check("messages become rows", loaded.length === 2 && loaded[1].role === "kokki" && loaded[1].failed === false)
    check("malformed entries are dropped",
          CE.messagesFromServer([{role: "bot", text: "x"}, {role: "you"}, "str", null, {role: "you", text: "ok"}]).length === 1)
    check("a non-list gives no rows", same(CE.messagesFromServer({detail: "x"}), []))

    // /help
    check("help lists every command", ["/new", "/history", "/open", "/help"].every(function(c) { return CE.helpText().indexOf(c) >= 0 }))
    check("help does not mention /more", CE.helpText().indexOf("/more") < 0)

    // the command menu shown while typing "/"
    var names = function(list) { return list.map(function(c) { return c.name }) }
    check("a lone slash lists every command in order", same(names(CE.commandSuggestions("/")), ["new", "history", "open", "help"]))
    check("typing filters by prefix", same(names(CE.commandSuggestions("/h")), ["history", "help"]))
    check("a longer prefix narrows it", same(names(CE.commandSuggestions("/he")), ["help"]))
    check("filtering ignores case", same(names(CE.commandSuggestions("/OPEN")), ["open"]))
    check("no match gives an empty menu", CE.commandSuggestions("/x").length === 0)
    check("plain text has no menu", CE.commandSuggestions("hello").length === 0 && CE.commandSuggestions("").length === 0)
    check("a space means you moved on to the argument, so no menu", CE.commandSuggestions("/open ").length === 0)
    check("a path is not a menu", CE.commandSuggestions("/etc/hosts").length === 0)
    check("each entry explains itself", CE.commandSuggestions("/")[0].description.length > 0 && CE.commandSuggestions("/")[2].usage === "/open <number>")
    check("/more is not offered", names(CE.commandSuggestions("/")).indexOf("more") < 0)

    // choosing from the menu
    var open = CE.commandSuggestions("/open")[0]
    var history = CE.commandSuggestions("/history")[0]
    check("a command that needs an argument is filled in, not run", same(CE.acceptSuggestion(open), {run: false, text: "/open "}))
    check("a command without arguments runs at once", same(CE.acceptSuggestion(history), {run: true, text: "/history"}))
    check("Tab completes the name and adds a space", CE.tabCompletion(history) === "/history " && CE.tabCompletion(open) === "/open ")
    check("the highlight moves down and wraps", CE.moveIndex(0, 1, 4) === 1 && CE.moveIndex(3, 1, 4) === 0)
    check("the highlight moves up and wraps", CE.moveIndex(2, -1, 4) === 1 && CE.moveIndex(0, -1, 4) === 3)
    check("an empty menu keeps the highlight at zero", CE.moveIndex(5, 1, 0) === 0)

    // waiting rules: a turn or a conversation switch must not start while something else is in flight
    check("nothing in flight: go ahead", CE.blockedReason(false, false) === "")
    check("a reply is streaming: busy", CE.blockedReason(true, false) === "busy")
    check("a history/open load is running: loading", CE.blockedReason(false, true) === "loading")
    check("both: the reply comes first", CE.blockedReason(true, true) === "busy")
    check("each wait has its own visible note", CE.waitNote("busy").length > 0 && CE.waitNote("loading").length > 0 && CE.waitNote("busy") !== CE.waitNote("loading"))
    check("no wait, no note", CE.waitNote("") === "")
    check("the loading note tells you to retry", CE.waitNote("loading").toLowerCase().indexOf("try again") >= 0)

    // safeMarkdown
    check("image -> link", CE.safeMarkdown("![a](http://x/y.png)") === "[a](http://x/y.png)")
    check("reference image -> link", CE.safeMarkdown("![b][r]") === "[b][r]")
    check("two images", CE.safeMarkdown("![a](u) ![b](v)") === "[a](u) [b](v)")
    check("plain text untouched", CE.safeMarkdown("Wow! **bold** [link](u)") === "Wow! **bold** [link](u)")
    check("non-string input tolerated", CE.safeMarkdown(42) === "42")

  }

  Component.onCompleted: {
    try { runChecks() } catch (e) { failures++; console.log("EXCEPTION: " + e) }
    console.log(failures === 0 ? "ALL PASSED" : failures + " FAILED")
    Qt.exit(failures === 0 ? 0 : 1)
  }
}

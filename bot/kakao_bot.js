// 메신저봇R — 레거시 API 방식
// 트리거방에서 "[직원]내용" 또는 "[알바]내용" 수신 시 해당 방으로 라우팅

var TRIGGER_ROOM = "트리거방";
var ROOMS = {
  "알바": "리와인드 휘트니스 중산점 인포방",
  "직원": "리와인드 휘트니스 중산점"
};

function response(room, msg, sender, isGroupChat, replier) {
  Log.i("받음: " + room + " | " + msg);

  if (room !== TRIGGER_ROOM) return;

  var match = msg.match(/^\[(직원|알바)\]([\s\S]+)/);
  if (!match) return;

  var key = match[1];
  var message = match[2].trim();
  var target = ROOMS[key];

  Log.i("전송 시도: " + target + " | " + message);

  if (target && message) {
    Api.replyRoom(target, message);
  }
}

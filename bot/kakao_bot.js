// 메신저봇R — Java ServerSocket HTTP 서버 방식
// PC에서 POST http://폰IP:9094 { "target": "직원"|"알바", "msg": "내용" }
// 레거시 API 체크 필요 (Api.replyRoom 사용)

try {
    var server = new java.net.ServerSocket();
    server.setReuseAddress(true);
    server.bind(new java.net.InetSocketAddress(9094));
    Log.i("HTTP 서버 시작");

    new java.lang.Thread(function () {
        var ROOMS = {"알바": "리와인드 휘트니스 중산점 인포방", "직원": "리와인드 휘트니스 중산점"};
        while (true) {
            try {
                var socket = server.accept();
                Log.i("연결됨");

                var reader = new java.io.BufferedReader(
                    new java.io.InputStreamReader(socket.getInputStream(), "UTF-8")
                );
                var out = socket.getOutputStream();

                var line, contentLength = 0;
                while ((line = reader.readLine()) !== null && line.length() > 0) {
                    if (("" + line).toLowerCase().startsWith("content-length:"))
                        contentLength = parseInt(("" + line).split(":")[1].trim());
                }

                var body = "";
                for (var i = 0; i < contentLength; i++) {
                    body += String.fromCharCode(reader.read());
                }
                Log.i("바디: " + body);

                var data = JSON.parse(body);
                var target = ROOMS[data.target];
                if (target && data.msg) {
                    Api.replyRoom(target, data.msg);
                    Log.i("전송: " + target);
                }

                var res = "HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok";
                out.write(new java.lang.String(res).getBytes("UTF-8"));
                out.flush();
                socket.close();
            } catch(e) {
                Log.i("오류: " + e);
            }
        }
    }).start();
} catch(e) {
    Log.i("서버 시작 실패: " + e);
}

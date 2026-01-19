from urllib.parse import urlencode
import cv2
from django.http import StreamingHttpResponse
from django.shortcuts import render, redirect

# 전역으로 카메라 열어두기 (간단 버전)
# (Windows 안정성용 CAP_DSHOW 옵션은 필요하면 추가)
cap = cv2.VideoCapture(0)

def index(request):
    return render(request, "stream/index.html")

def frame_generator():
    """
    MJPEG 스트림용 제너레이터
    """
    if not cap.isOpened():
        raise RuntimeError("웹캠을 열 수 없습니다. index(0/1/2)나 권한을 확인하세요.")

    while True:
        ok, frame = cap.read()
        if not ok:
            continue

        # (선택) frame 처리 가능: 텍스트 오버레이 등
        cv2.putText(frame, "Hello", (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2)

        ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if not ok:
            continue

        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")

def video_feed(request):
    return StreamingHttpResponse(
        frame_generator(),
        content_type="multipart/x-mixed-replace; boundary=frame"
    )




def login_page(request):
    return render(request, "stream/login.html")

def nickname_page(request):
    if request.method == "POST":
        nickname = request.POST.get("nickname", "").strip()

        if nickname:
            # ✅ query string으로 전달
            query = urlencode({"nickname": nickname})
            return redirect(f"/stream/?{query}")

    return render(request, "stream/nickname.html")

def game_page(request):
    nickname = request.GET.get("nickname", "Guest")
    return render(request, "game_webcam.html", {"nickname": nickname})

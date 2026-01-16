import cv2
import time
from collections import deque
from datetime import datetime

import mediapipe as mp

# -----------------------------
# Gesture definitions (5)
# -----------------------------
GESTURES = [
    "OPEN_PALM",   # all 5 fingers up
    "FIST",        # all down
    "THUMBS_UP",   # only thumb up
    "PEACE",       # index + middle up
    "POINT",       # only index up
]
# POINT & THUMS_UP 겹치는 issue 있음

mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils


def _finger_up_states(hand_landmarks, handedness_label):
    """
    Returns dict of {thumb, index, middle, ring, pinky}: bool (up/down)
    Heuristic-based using landmark coordinates.
    """
    lm = hand_landmarks.landmark

    # Landmark indices (MediaPipe Hands)
    TH_TIP, TH_IP, TH_MCP = 4, 3, 2
    IN_TIP, IN_PIP = 8, 6
    MI_TIP, MI_PIP = 12, 10
    RI_TIP, RI_PIP = 16, 14
    PI_TIP, PI_PIP = 20, 18

    # For fingers except thumb: "up" if TIP is above PIP in image (y smaller)
    index_up = lm[IN_TIP].y < lm[IN_PIP].y
    middle_up = lm[MI_TIP].y < lm[MI_PIP].y
    ring_up = lm[RI_TIP].y < lm[RI_PIP].y
    pinky_up = lm[PI_TIP].y < lm[PI_PIP].y

    # Thumb heuristic
    thumb_vertical_up = lm[TH_TIP].y < lm[TH_IP].y

    if handedness_label == "Right":
        thumb_open = lm[TH_TIP].x < lm[TH_MCP].x
    else:  # "Left"
        thumb_open = lm[TH_TIP].x > lm[TH_MCP].x

    thumb_up = thumb_vertical_up or thumb_open

    return {
        "thumb": thumb_up,
        "index": index_up,
        "middle": middle_up,
        "ring": ring_up,
        "pinky": pinky_up,
    }


def classify_gesture(states):
    """
    states: dict thumb/index/middle/ring/pinky -> bool
    Returns one of GESTURES or "UNKNOWN"
    """
    t = states["thumb"]
    i = states["index"]
    m = states["middle"]
    r = states["ring"]
    p = states["pinky"]

    up_count = sum([t, i, m, r, p])

    if up_count == 0:
        return "FIST"

    if up_count == 5:
        return "OPEN_PALM"

    if t and not (i or m or r or p):
        return "THUMBS_UP"

    if i and m and not (t or r or p):
        return "PEACE"

    if i and not (t or m or r or p):
        return "POINT"

    return "UNKNOWN"


def stable_label(label_queue):
    """
    Simple temporal smoothing: choose the most frequent label in recent frames.
    """
    if not label_queue:
        return "UNKNOWN"
    freq = {}
    for x in label_queue:
        freq[x] = freq.get(x, 0) + 1
    return max(freq.items(), key=lambda kv: kv[1])[0]


def hand_bbox_px(hand_landmarks, w, h):
    """
    Compute bounding box of the hand landmarks in pixel coordinates.
    Returns (x, y, bw, bh) clipped to image bounds.
    """
    xs = [lm.x for lm in hand_landmarks.landmark]
    ys = [lm.y for lm in hand_landmarks.landmark]
    x1 = int(min(xs) * w)
    y1 = int(min(ys) * h)
    x2 = int(max(xs) * w)
    y2 = int(max(ys) * h)

    # clip
    x1 = max(0, min(w - 1, x1))
    y1 = max(0, min(h - 1, y1))
    x2 = max(0, min(w - 1, x2))
    y2 = max(0, min(h - 1, y2))

    return x1, y1, (x2 - x1), (y2 - y1)


def log_gesture(gesture, handedness, bbox):
    """
    Print gesture log: type, position, time.
    bbox: (x, y, w, h) in pixels
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    x, y, bw, bh = bbox
    cx = x + bw // 2
    cy = y + bh // 2
    print(f"[{ts}] gesture={gesture} hand={handedness} bbox=(x={x},y={y},w={bw},h={bh}) center=(x={cx},y={cy})")


def main(camera_index=0):
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera index {camera_index}")

    recent = deque(maxlen=10)

    # last logged stable gesture (avoid log spam)
    last_logged = None

    with mp_hands.Hands(
        model_complexity=1,
        max_num_hands=1,
        min_detection_confidence=0.6,
        min_tracking_confidence=0.6,
    ) as hands:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            result = hands.process(rgb)
            rgb.flags.writeable = True

            gesture = "NO_HAND"
            handedness = ""
            bbox = None

            if result.multi_hand_landmarks and result.multi_handedness:
                hand_landmarks = result.multi_hand_landmarks[0]
                handedness = result.multi_handedness[0].classification[0].label  # "Left"/"Right"

                mp_draw.draw_landmarks(
                    frame,
                    hand_landmarks,
                    mp_hands.HAND_CONNECTIONS,
                    mp_draw.DrawingSpec(thickness=2, circle_radius=2),
                    mp_draw.DrawingSpec(thickness=2),
                )

                states = _finger_up_states(hand_landmarks, handedness)
                raw_gesture = classify_gesture(states)

                recent.append(raw_gesture)
                gesture = stable_label(recent)

                bbox = hand_bbox_px(hand_landmarks, w, h)

                # draw bbox
                x, y, bw, bh = bbox
                cv2.rectangle(frame, (x, y), (x + bw, y + bh), (255, 255, 255), 2)

                # Optional: show finger states
                states_text = f"T:{int(states['thumb'])} I:{int(states['index'])} M:{int(states['middle'])} R:{int(states['ring'])} P:{int(states['pinky'])}"
                cv2.putText(frame, states_text, (10, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

                # Log only when one of the 5 gestures is stably detected and changed
                if gesture in GESTURES and gesture != last_logged and bbox is not None:
                    log_gesture(gesture, handedness, bbox)
                    last_logged = gesture

            else:
                recent.clear()
                last_logged = None  # 손이 사라지면 다음에 다시 같은 제스처도 로그 찍히게 리셋

            title = f"Hand: {handedness or '-'}  Gesture: {gesture}"
            cv2.putText(frame, title, (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

            cv2.imshow("MediaPipe Hand Gesture (5-class)", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == 27 or key == ord("q"):
                break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main(camera_index=0)

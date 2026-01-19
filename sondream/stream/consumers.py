import json
import time
from channels.generic.websocket import AsyncWebsocketConsumer
from .rhythm_game_logic import (
    PlayState, NoteEvent, NoteType, process_note_result, 
    TimingConfig, SpatialConfig, Judgement
)

NOTE_INTERVALS = [
  0.209, 1.858, 1.835, 1.835, 0.928, 1.254, 1.347, 1.324, 0.348, 0.464,
  1.022, 1.858, 1.347, 1.161, 1.022, 1.858, 2.508, 1.672, 3.46, 0.326,
  2.322, 4.389, 1.254, 1.649, 1.858, 1.347, 0.928, 2.415, 1.812, 1.857,
  1.022, 1.857, 1.254, 0.72, 1.277, 1.138, 1.858, 2.183, 1.138, 1.277,
  1.138, 1.857, 1.254, 0.72, 1.277, 3.692, 1.161, 1.602, 1.277, 2.554,
  1.138, 1.161, 1.649, 1.649, 1.625, 1.161, 1.138, 0.813, 0.882, 1.649
]

class RhythmGameConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        print(">>> [DEBUG] WebSocket 연결 시도...")
        await self.accept()
        print(">>> [DEBUG] WebSocket 연결 성공!")
        
        self.state = PlayState()
        self.note_index = 0
        self.current_target_time = 0.0
        
        await self.send(text_data=json.dumps({
            'type': 'system',
            'message': 'Connected. Waiting for start...',
            'state': 'MENU'
        }))

    async def disconnect(self, close_code):
        pass

    def get_next_note_time(self):
        if self.note_index < len(NOTE_INTERVALS):
            interval = NOTE_INTERVALS[self.note_index]
            if self.note_index == 0:
                # [수정] 음악과 싱크를 맞추기 위해 불필요한 1000ms 딜레이 제거
                # 음악 시작과 동시에 T=0이므로, 첫 노트는 현재시간 + 첫 간격
                self.current_target_time = time.time() * 1000 + (interval * 1000)
            else:
                self.current_target_time += (interval * 1000)
            return self.current_target_time
        return None

    def calculate_final_rank(self):
        if self.state.max_possible_score <= 0: return "F"
        ratio = self.state.total_score / self.state.max_possible_score
        
        if ratio >= 0.90: return "S"
        elif ratio >= 0.80: return "A"
        elif ratio >= 0.70: return "B"
        elif ratio >= 0.60: return "C"
        return "F"

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            action = data.get('action')
            
            if action == 'game_start':
                print(">>> [DEBUG] 게임 시작!")
                self.state = PlayState()
                self.note_index = 0
                
                next_time = self.get_next_note_time()
                
                await self.send(text_data=json.dumps({
                    'type': 'game_start',
                    'message': 'Game Started!'
                }))
                
                await self.send(text_data=json.dumps({
                    'type': 'next_target',
                    'target_start': next_time
                }))
                return

            if action == 'gesture_complete' or action == 'miss':
                actual_entry = data.get('entry_time', -1)
                min_dist = data.get('min_dist', 9999)
                
                if action == 'miss':
                    actual_entry = -1

                note_event = NoteEvent(
                    note_type=NoteType.TAP,
                    target_start=self.current_target_time,
                    target_x=100, target_y=100, 
                    actual_entry=actual_entry,
                    min_dist=min_dist
                )

                result = process_note_result(
                    note=note_event,
                    state=self.state,
                    t_cfg=TimingConfig(), 
                    s_cfg=SpatialConfig()
                )
                
                await self.send(text_data=json.dumps({
                    'type': 'result',
                    'data': result
                }))
                
                self.note_index += 1
                next_time = self.get_next_note_time()
                
                if next_time:
                    await self.send(text_data=json.dumps({
                        'type': 'next_target',
                        'target_start': next_time
                    }))
                else:
                    final_rank = self.calculate_final_rank()
                    await self.send(text_data=json.dumps({
                        'type': 'game_over',
                        'total_score': round(self.state.total_score, 1),
                        'max_possible_score': round(self.state.max_possible_score, 1),
                        'rank': final_rank
                    }))

        except Exception as e:
            print(f">>> [ERROR] : {e}")
import math
from dataclasses import dataclass
from enum import Enum, auto
from typing import Tuple

# ---------------------------------------------------------
# 1. Enums & Constants
# ---------------------------------------------------------

class Judgement(Enum):
    PERFECT = auto() # 100%
    GREAT = auto()   # 50% ~ 99%
    GOOD = auto()    # 1% ~ 49%
    BAD = auto()     # 0% (Combo Break)
    MISS = auto()    # 아예 안 침

class NoteType(Enum):
    TAP = auto()
    HOLD = auto()

# ---------------------------------------------------------
# 2. Config Classes
# ---------------------------------------------------------

@dataclass
class TimingConfig:
    window_perfect: float = 416 
    excess_max: float = 416 
    cut_great: float = 50.0  

@dataclass
class ComboConfig:
    growth_a: float = 0.01
    growth_p: float = 1.2
    bonus_cap_multiplier: float = 2.0

@dataclass
class FeverConfig:
    fill_perfect: int = 10
    fill_great: int = 5
    fill_good: int = 2
    fill_bad: int = 0
    fill_miss: int = 0
    
    gauge_max: int = 100
    fever_duration_notes: int = 10
    score_multiplier: float = 2.0

@dataclass
class SpatialConfig:
    target_radius: float = 100.0

# ---------------------------------------------------------
# 3. Data Structures
# ---------------------------------------------------------

@dataclass
class NoteEvent:
    note_type: NoteType
    target_start: float
    target_x: float
    target_y: float
    actual_entry: float
    min_dist: float
    # Legacy fields
    target_end: float = 0.0 
    actual_exit: float = 0.0

@dataclass
class PlayState:
    total_score: float = 0.0
    max_possible_score: float = 0.0
    current_combo: int = 0
    max_combo: int = 0
    fever_gauge: int = 0
    fever_active_notes: int = 0

    def is_fever_active(self) -> bool:
        return self.fever_active_notes > 0

# ---------------------------------------------------------
# 4. Helper Functions
# ---------------------------------------------------------

def calc_excess(diff_ms: float, window: float) -> float:
    abs_diff = abs(diff_ms)
    if abs_diff > window:
        return abs_diff - window
    return 0.0

def get_excess_ratio(excess_ms: float, max_excess: float) -> float:
    return min(excess_ms / max_excess, 1.0)

# ---------------------------------------------------------
# 5. Scoring Logic
# ---------------------------------------------------------

def calculate_base_score(note: NoteEvent, t_cfg: TimingConfig, s_cfg: SpatialConfig) -> Tuple[float, Judgement]:
    # MISS 처리 (시간 내에 입력 없음)
    if note.actual_entry == -1:
        return 0.0, Judgement.MISS

    # 위치 판정
    if note.min_dist > s_cfg.target_radius:
        return 0.0, Judgement.BAD

    # 시간 판정
    diff = note.actual_entry - note.target_start
    abs_diff = abs(diff)
    W = t_cfg.window_perfect

    if abs_diff <= W:
        return 100.0, Judgement.PERFECT
    
    excess = abs_diff - W
    penalty_ratio = get_excess_ratio(excess, t_cfg.excess_max)
    
    if penalty_ratio >= 1.0:
        return 0.0, Judgement.BAD

    score = 100.0 * (1.0 - penalty_ratio)

    if score <= 0.0:
        return 0.0, Judgement.BAD
    elif score >= t_cfg.cut_great:
        return score, Judgement.GREAT
    else:
        return score, Judgement.GOOD


def process_note_result(
    note: NoteEvent,
    state: PlayState,
    t_cfg: TimingConfig = TimingConfig(),
    s_cfg: SpatialConfig = SpatialConfig(),
    c_cfg: ComboConfig = ComboConfig(),
    f_cfg: FeverConfig = FeverConfig()
) -> dict:
    
    base_score, judgement = calculate_base_score(note, t_cfg, s_cfg)
    
    if judgement in (Judgement.BAD, Judgement.MISS):
        state.current_combo = 0
        final_score = 0.0
    else:
        state.current_combo += 1
        state.max_combo = max(state.max_combo, state.current_combo)
        
        bonus_ratio = c_cfg.growth_a * (state.current_combo ** c_cfg.growth_p)
        bonus_score = base_score * bonus_ratio
        max_bonus = base_score * c_cfg.bonus_cap_multiplier
        bonus_score = min(bonus_score, max_bonus)
        
        current_note_total = base_score + bonus_score
        
        if state.is_fever_active():
            state.fever_active_notes -= 1
            current_note_total *= f_cfg.score_multiplier
        
        final_score = current_note_total

    # 피버 게이지 충전
    if not state.is_fever_active():
        fill_amt = {
            Judgement.PERFECT: f_cfg.fill_perfect,
            Judgement.GREAT: f_cfg.fill_great,
            Judgement.GOOD: f_cfg.fill_good,
            Judgement.BAD: f_cfg.fill_bad,
            Judgement.MISS: f_cfg.fill_miss
        }.get(judgement, 0)
        
        state.fever_gauge += fill_amt
        if state.fever_gauge >= f_cfg.gauge_max:
            state.fever_gauge = 0
            state.fever_active_notes = f_cfg.fever_duration_notes

    state.total_score += final_score

    # Max Score Simulation (피버 배율 제외)
    simulated_max_combo = state.max_combo + 1 if judgement in (Judgement.BAD, Judgement.MISS) else state.current_combo
    max_base = 100.0
    max_bonus_ratio = c_cfg.growth_a * (simulated_max_combo ** c_cfg.growth_p)
    max_bonus_val = min(max_base * max_bonus_ratio, max_base * c_cfg.bonus_cap_multiplier)
    
    mult = f_cfg.score_multiplier if state.is_fever_active() else 1.0
    possible_score = (max_base + max_bonus_val) * mult
    
    state.max_possible_score += possible_score
    
    rank_ratio = (state.total_score / state.max_possible_score) if state.max_possible_score > 0 else 0.0
    rank = "F"
    if rank_ratio >= 0.90: rank = "S"
    elif rank_ratio >= 0.80: rank = "A"
    elif rank_ratio >= 0.70: rank = "B"
    elif rank_ratio >= 0.60: rank = "C"

    return {
        "judgement": judgement.name,
        "base_score": round(base_score, 1),
        "final_score": round(final_score, 1),
        "combo": state.current_combo,
        "fever_active": state.is_fever_active(),
        "fever_gauge": state.fever_gauge,
        "fever_max": f_cfg.gauge_max,
        "fever_active_notes": state.fever_active_notes,
        "fever_duration": f_cfg.fever_duration_notes,
        "total_score": round(state.total_score, 1),
        "rank": rank,
        "debug_in": f"{note.actual_entry - note.target_start:.1f}" if note.actual_entry != -1 else "MISS",
    }
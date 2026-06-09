import numpy as np
from scipy.signal import find_peaks, butter, filtfilt, detrend
import onnxruntime as ort
from dataclasses import dataclass
from typing import List, Optional, Tuple

@dataclass
class BpFeatures:
    # Base Timing
    pttf: float
    pttd: float
    d_ptt: float
    d_ptt_norm: float

    # Morphology
    up_slope: float
    pw50: float
    dia_slope: float
    auc: float
    acdc: float

    # HRV & Quality
    rr_mean: float
    rr_std: float
    corr_mean: float
    keep_ratio: float

    def to_model_input(self, base_value: float, base_features: 'BpFeatures') -> np.ndarray:
        # Kotlin의 toModelInput 로직과 동일 (Current - Base)
        features = [
            self.pttf - base_features.pttf,
            self.pttd - base_features.pttd,
            self.rr_mean - base_features.rr_mean,
            self.rr_std - base_features.rr_std,
            self.acdc - base_features.acdc,
            self.up_slope - base_features.up_slope,
            self.pw50 - base_features.pw50,
            self.dia_slope - base_features.dia_slope,
            self.auc - base_features.auc,
            self.corr_mean - base_features.corr_mean,
            self.d_ptt - base_features.d_ptt,
            self.d_ptt_norm - base_features.d_ptt_norm,
            base_value
        ]
        return np.array(features, dtype=np.float32).reshape(1, -1)

class BpManager:
    TARGET_SAMPLE_COUNT = 20000
    REMOVE_SIZE = 500
    FS = 500.0
    EPS = 1e-12
    MIN_KEEP_BEATS = 10
    CORR_THRESHOLD = 0.94
    WINDOW_FACTOR = 1.2

    def __init__(self, sbp_model_path: str, dbp_model_path: str, base_sbp: float, base_dbp: float, base_features = None):
        # ONNX 세션 초기화
        self.sbp_session = ort.InferenceSession(sbp_model_path)
        self.dbp_session = ort.InferenceSession(dbp_model_path)

        self.base_sbp = base_sbp
        self.base_dbp = base_dbp
        self.base_features = base_features

        self.ecg_buffer = []
        self.ir_buffer = []

    def moving_average(self, data: np.ndarray, window: int) -> np.ndarray:
        return np.convolve(data, np.ones(window)/window, mode='same')

    def butter_filter(self, data: np.ndarray, cutoff: float, order: int, btype: str) -> np.ndarray:
        nyq = 0.5 * self.FS
        normal_cutoff = cutoff / nyq
        b, a = butter(order, normal_cutoff, btype=btype, analog=False)
        return filtfilt(b, a, data)

    def process_data(self, ecg_raw: np.ndarray, ir_raw: np.ndarray) -> Optional[BpFeatures]:
        try:
            if len(ecg_raw) == 0 or len(ir_raw) == 0 or len(ecg_raw) != len(ir_raw):
                print("ECG or IR data is empty or has different lengths.")
                return None

            # 1. Preprocess
            ecg_smooth = self.moving_average(ecg_raw, 5)

            # IR AC: HP(0.7) -> LP(10) -> Mov(5)
            ir_ac = self.butter_filter(ir_raw, 0.7, 2, 'high')
            ir_ac = self.butter_filter(ir_ac, 10.0, 4, 'low')
            ir_ac = self.moving_average(ir_ac, 5)

            # IR DC: LP(0.3) -> Mov(5)
            ir_dc = self.butter_filter(ir_raw, 0.3, 4, 'low')
            ir_dc = self.moving_average(ir_dc, 5)

            # 30초 window에서 앞 5초/뒤 5초를 제외하고 중간 20초만 분석합니다.
            trim_count = int(5 * self.FS)
            start_idx, end_idx = trim_count, len(ir_ac) - trim_count

            if start_idx >= end_idx:
                print("Data too short for trimming.")
                return None

            ecg_smooth = ecg_smooth[start_idx:end_idx]
            ir_ac = ir_ac[start_idx:end_idx]
            ir_dc = ir_dc[start_idx:end_idx]
            dc_val = np.median(ir_dc)

            # 2. R-Peak Detection
            # Kotlin의 detectPeaks 로직은 scipy의 find_peaks와 매우 유사합니다.
            ecg_locs, _ = find_peaks(ecg_smooth, distance=200, prominence=400.0)

            if len(ecg_locs) < 5: return None

            # 3. RR Features
            rr_intervals = np.diff(ecg_locs) / self.FS
            rr_mean = np.mean(rr_intervals)

            # Trimmed STD (k=5)
            if len(rr_intervals) >= 12:
                sorted_rr = np.sort(rr_intervals)
                trimmed_rr = sorted_rr[5:-5]
                rr_std = np.std(trimmed_rr, ddof=1)
            else:
                rr_std = np.nan

            # 4. Beat Segmentation
            avg_diff = np.mean(np.diff(ecg_locs))
            win = int(round(avg_diff * self.WINDOW_FACTOR))
            hw = win // 2

            ir_beats = []
            for idx in ecg_locs:
                start, end = idx - hw, idx + hw
                if start >= 0 and end < len(ir_ac):
                    ir_beats.append(ir_ac[start:end])

            if not ir_beats:
                print("No beats detected.")
                return None

            # 5. Correlation Filtering
            ir_beats = np.array(ir_beats)
            mean_template = np.mean(ir_beats, axis=0)

            kept_beats = []
            corr_values = []

            for beat in ir_beats:
                r = np.corrcoef(beat, mean_template)[0, 1]
                if not np.isnan(r) and r >= self.CORR_THRESHOLD:
                    kept_beats.append(beat)
                    corr_values.append(r)

            if len(kept_beats) < self.MIN_KEEP_BEATS:
                print("Not enough beats after correlation filtering.")
                return None

            corr_mean = np.mean(corr_values)
            keep_ratio = len(kept_beats) / len(ir_beats)

            # 6. Final Template
            ir_template = np.mean(kept_beats, axis=0)
            n_samples = len(ir_template)
            t_template = (np.arange(n_samples) - hw) / self.FS
            mid = n_samples // 2

            # 7. Feature Extraction
            # PTTf
            right_part = ir_template[mid:]
            posi_idx = mid + np.argmax(right_part)
            pttf = t_template[posi_idx]

            # PTTd
            pttd = self.find_dicrotic_notch(ir_template, t_template, posi_idx)

            # Upstroke Slope
            up_slope = np.nan
            if posi_idx > mid:
                up_section = ir_template[mid:posi_idx+1]
                if len(up_section) > 1:
                    up_slope = np.max(np.diff(up_section)) * self.FS

            # AC/DC
            ac_val = np.max(ir_template) - np.min(ir_template)
            acdc = ac_val / (dc_val + self.EPS)

            # PW50
            wave = ir_template - ir_template[mid]
            pw50 = np.nan
            amp = np.max(wave) - np.min(wave)
            if amp >= 1e-6:
                half_level = np.min(wave) + 0.5 * amp
                left_idx = np.where(wave[:posi_idx+1] <= half_level)[0]
                right_idx = np.where(wave[posi_idx:] <= half_level)[0]
                if left_idx.size > 0 and right_idx.size > 0:
                    pw50 = t_template[posi_idx + right_idx[0]] - t_template[left_idx[-1]]

            # Diastolic Slope
            dia_slope = np.nan
            d1_idx = posi_idx + int(round(0.05 * self.FS))
            d2_idx = min(posi_idx + int(round(0.25 * self.FS)), n_samples - 1)
            if d1_idx < d2_idx:
                dia_slope = (ir_template[d2_idx] - ir_template[d1_idx]) / (t_template[d2_idx] - t_template[d1_idx])

            # AUC (Trapz)
            seg_auc = np.maximum(wave[mid:], 0)
            auc = np.trapezoid(seg_auc, t_template[mid:])

            # Derived
            d_ptt = pttd - pttf if not np.isnan(pttd) else np.nan
            d_ptt_norm = d_ptt / rr_mean if not np.isnan(d_ptt) else np.nan

            return BpFeatures(
                pttf, pttd, d_ptt, d_ptt_norm,
                up_slope, pw50, dia_slope, auc, acdc,
                rr_mean, rr_std, corr_mean, keep_ratio
            )

        except Exception as e:
            print(f"Error in processing: {e}")
            return None

    def find_dicrotic_notch(self, signal: np.ndarray, t_template: np.ndarray, peak_idx: int) -> float:
        n = len(signal)
        # d2 calculation
        d1 = np.diff(signal)
        d2 = np.zeros(n)
        d2[2:] = np.diff(d1)
        d2_smooth = self.moving_average(d2, 5)

        tail_seg = signal[peak_idx:]
        if tail_seg.size == 0: return np.nan

        tail_min = np.percentile(tail_seg, 5)
        amp = signal[peak_idx] - tail_min
        if amp < 1e-6: return np.nan

        level70 = signal[peak_idx] - 0.7 * amp
        rel30 = np.where(tail_seg <= level70)[0]
        if rel30.size == 0: return np.nan

        s1 = peak_idx + rel30[0]
        s2 = min(s1 + int(round(0.40 * self.FS)), n - 1)

        if s1 < s2:
            seg2 = d2_smooth[s1:s2+1]
            prom = max(0.0, 0.1 * np.std(seg2))
            locs, _ = find_peaks(seg2, distance=1, prominence=prom)

            # Positive peaks only
            positive_locs = [l for l in locs if seg2[l] > 0]
            if positive_locs:
                return t_template[s1 + positive_locs[0]]
            else:
                # Fallback: zero-crossing
                z = np.where(seg2 > 0)[0]
                if z.size > 0: return t_template[s1 + z[0]]

        return np.nan

    def predict_blood_pressure(self, features: BpFeatures) -> Tuple[float, float]:
        # SBP Prediction
        input_sbp = features.to_model_input(self.base_sbp, self.base_features)
        sbp_name = self.sbp_session.get_inputs()[0].name
        sbp_val = self.sbp_session.run(None, {sbp_name: input_sbp})[0][0][0]

        # DBP Prediction
        input_dbp = features.to_model_input(self.base_dbp, self.base_features)
        dbp_name = self.dbp_session.get_inputs()[0].name
        dbp_val = self.dbp_session.run(None, {dbp_name: input_dbp})[0][0][0]

        return float(sbp_val), float(dbp_val)

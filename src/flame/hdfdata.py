import os
import h5py
import numpy as np
from scipy.optimize import curve_fit


class HdfData:
    def __init__(self, filepath):
        self.filepath = filepath
        self.basename = os.path.basename(filepath)
        with h5py.File(filepath, "r") as f:
            uid = list(f.keys())[0]
            primary = f[uid + "/instrument/bluesky/streams/primary"]
            self.energies = primary["monochromator-energy/value"][:]
            self.spectra = primary["ge_13element/value"][:]
            self.n_points, self.n_elements, self.n_channels = self.spectra.shape
            self.dt_factors = np.zeros((self.n_points, self.n_elements))
            for det in range(self.n_elements):
                self.dt_factors[:, det] = primary[
                    "ge_13element-element{}-deadtime_factor/value".format(det)
                ][:]
            self.scalar_signals = {}
            self.scalar_signal_names = []
            for key in sorted(primary.keys()):
                if key == "monochromator-energy":
                    continue
                val_path = key + "/value"
                if val_path in primary:
                    ds = primary[val_path]
                    if ds.ndim == 1 and ds.shape[0] == self.n_points:
                        full_name = key + "/value"
                        self.scalar_signals[full_name] = ds[:]
                        self.scalar_signal_names.append(full_name)

        self.uid = uid
        self.cal_scale = np.ones(self.n_elements)
        self.cal_offset = np.zeros(self.n_elements)
        self.cal_peaks = None
        self.calibrated = False

    @staticmethod
    def export_transmission_columns(hdf5_path, out_path, delimiter="\t"):
        with h5py.File(hdf5_path, "r") as f:
            uid = list(f.keys())[0]
            primary = f[uid + "/instrument/bluesky/streams/primary"]

            def read_1d(name):
                ds = primary[name + "/value"]
                arr = np.asarray(ds[:], dtype=float)
                if arr.ndim != 1:
                    raise ValueError("Expected 1D dataset for {}".format(name))
                return arr

            energy = np.asarray(primary["monochromator-energy/value"][:], dtype=float)
            ipreslit = read_1d("Ipreslit-count")
            iprekb = read_1d("IpreKB-count")
            i0 = read_1d("I0-count")
            it = read_1d("It-count")
            iref = read_1d("Iref-count")

        n = len(energy)
        cols = [ipreslit, iprekb, i0, it, iref]
        for c in cols:
            if len(c) != n:
                raise ValueError("Column length mismatch")

        header = delimiter.join(["mono-energy", "Ipreslit-count", "IpreKB-count", "I0-count", "It-count", "Iref-count"])
        data = np.column_stack([energy, ipreslit, iprekb, i0, it, iref])
        np.savetxt(out_path, data, delimiter=delimiter, header=header, comments="")

    def get_scalar_signal(self, name):
        return self.scalar_signals.get(name, np.ones(self.n_points))

    @property
    def iprekb(self):
        return self.get_scalar_signal("IpreKB-count/value")

    @staticmethod
    def _find_peak_center_xcorr(ref_roi, det_spectrum, roi_lo, max_shift=80):
        search_lo = max(0, roi_lo - max_shift)
        search_hi = min(len(det_spectrum), roi_lo + len(ref_roi) + max_shift)
        det_search = det_spectrum[search_lo:search_hi].astype(float)
        ref = ref_roi.astype(float)
        if len(det_search) < len(ref):
            return None
        corr = np.correlate(det_search, ref, mode="valid")
        if len(corr) == 0:
            return None
        pk = np.argmax(corr)
        if pk > 0 and pk < len(corr) - 1:
            y0, y1, y2 = corr[pk - 1], corr[pk], corr[pk + 1]
            denom = 2.0 * (2.0 * y1 - y0 - y2)
            if abs(denom) > 1e-10:
                sub = (y0 - y2) / denom
            else:
                sub = 0.0
            shift = pk + sub
        else:
            shift = float(pk)
        det_peak_offset = search_lo + shift
        ref_roi_center = roi_lo + np.argmax(ref_roi)
        ref_sub = ref_roi_center
        pk_ref = np.argmax(ref_roi)
        if pk_ref > 0 and pk_ref < len(ref_roi) - 1:
            y0, y1, y2 = ref[pk_ref - 1], ref[pk_ref], ref[pk_ref + 1]
            denom = 2.0 * (2.0 * y1 - y0 - y2)
            if abs(denom) > 1e-10:
                ref_sub = roi_lo + pk_ref + (y0 - y2) / denom
        det_center = det_peak_offset + (ref_sub - roi_lo)
        return ref_sub, det_center

    @staticmethod
    def _find_peaks_auto(spectrum, min_height_frac=0.05, min_distance=50,
                         margin=50):
        from scipy.signal import find_peaks as sp_find_peaks
        s = spectrum.astype(float)
        s_safe = s[margin:len(s) - margin]
        threshold = s_safe.max() * min_height_frac
        peaks, props = sp_find_peaks(s_safe, height=threshold, distance=min_distance,
                                     prominence=threshold * 0.3)
        peaks = peaks + margin
        if len(peaks) < 2:
            return peaks
        heights = s[peaks]
        order = np.argsort(heights)[::-1]
        top = peaks[order[:min(8, len(order))]]
        best_score = -1
        best_pair = (top[0], top[1])
        for i in range(len(top)):
            for j in range(i + 1, len(top)):
                separation = abs(float(top[i]) - float(top[j]))
                strength = min(s[top[i]], s[top[j]])
                score = separation * strength
                if score > best_score:
                    best_score = score
                    best_pair = (min(top[i], top[j]), max(top[i], top[j]))
        return np.array([best_pair[0], best_pair[1]])

    def calibrate_linear(self, ref_element=0, peak1_range=None, peak2_range=None):
        ref_spectrum = self.spectra[-1, ref_element, :].astype(float)

        if peak1_range is None or peak2_range is None:
            auto_peaks = self._find_peaks_auto(ref_spectrum)
            if len(auto_peaks) < 2:
                return None, "Need at least 2 peaks in reference spectrum"
            sep = []
            for i in range(len(auto_peaks)):
                for j in range(i + 1, len(auto_peaks)):
                    sep.append((abs(auto_peaks[i] - auto_peaks[j]), i, j))
            sep.sort(reverse=True)
            best_i, best_j = sep[0][1], sep[0][2]
            p1, p2 = sorted([auto_peaks[best_i], auto_peaks[best_j]])
            hw = 40
            peak1_range = (max(0, int(p1) - hw), min(self.n_channels, int(p1) + hw))
            peak2_range = (max(0, int(p2) - hw), min(self.n_channels, int(p2) + hw))

        ref_roi1 = ref_spectrum[peak1_range[0]:peak1_range[1]]
        ref_roi2 = ref_spectrum[peak2_range[0]:peak2_range[1]]

        if ref_roi1.max() <= 0 or ref_roi2.max() <= 0:
            return None, "Reference peak regions have no signal"

        ref_c1_sub = peak1_range[0] + np.argmax(ref_roi1)
        ref_c2_sub = peak2_range[0] + np.argmax(ref_roi2)
        pk1 = np.argmax(ref_roi1)
        if pk1 > 0 and pk1 < len(ref_roi1) - 1:
            y0, y1, y2 = ref_roi1[pk1-1], ref_roi1[pk1], ref_roi1[pk1+1]
            d = 2.0 * (2.0*y1 - y0 - y2)
            if abs(d) > 1e-10:
                ref_c1_sub = peak1_range[0] + pk1 + (y0 - y2) / d
        pk2 = np.argmax(ref_roi2)
        if pk2 > 0 and pk2 < len(ref_roi2) - 1:
            y0, y1, y2 = ref_roi2[pk2-1], ref_roi2[pk2], ref_roi2[pk2+1]
            d = 2.0 * (2.0*y1 - y0 - y2)
            if abs(d) > 1e-10:
                ref_c2_sub = peak2_range[0] + pk2 + (y0 - y2) / d

        self.cal_peaks = (peak1_range, peak2_range, ref_c1_sub, ref_c2_sub)
        self.cal_scale = np.ones(self.n_elements)
        self.cal_offset = np.zeros(self.n_elements)
        results = []

        for det in range(self.n_elements):
            det_spectrum = self.spectra[-1, det, :].astype(float)
            r1 = self._find_peak_center_xcorr(ref_roi1, det_spectrum,
                                               peak1_range[0], max_shift=80)
            r2 = self._find_peak_center_xcorr(ref_roi2, det_spectrum,
                                               peak2_range[0], max_shift=80)
            if r1 is None or r2 is None:
                results.append((det, 1.0, 0.0, None, None, False))
                continue
            ref_c1, det_c1 = r1
            ref_c2, det_c2 = r2
            if abs(det_c2 - det_c1) < 1.0:
                results.append((det, 1.0, 0.0, det_c1, det_c2, False))
                continue
            scale = (ref_c2 - ref_c1) / (det_c2 - det_c1)
            offset = ref_c1 - scale * det_c1
            self.cal_scale[det] = scale
            self.cal_offset[det] = offset
            results.append((det, scale, offset, det_c1, det_c2, True))

        self.calibrated = True
        return results, "OK"

    @staticmethod
    def _gauss_plus_linear(x, a, mu, sigma, m, b):
        return a * np.exp(-0.5 * ((x - mu) / sigma) ** 2) + m * x + b

    def fit_peak(self, energy_idx, det, bg_lo, bg_hi, peak_lo, peak_hi,
                 apply_cal=True):
        spectrum = self.get_spectrum(energy_idx, det, apply_cal=apply_cal)
        channels = np.arange(bg_lo, bg_hi, dtype=float)
        y = spectrum[bg_lo:bg_hi].astype(float)
        peak_slice = spectrum[peak_lo:peak_hi].astype(float)
        bg_est = np.mean(np.concatenate([y[:10], y[-10:]]))
        peak_est = peak_slice.max() - bg_est
        center_guess = peak_lo + np.argmax(peak_slice)
        if peak_est < 1:
            return {"area": 0.0, "ok": False}
        p0 = [peak_est, center_guess, 15.0, 0.0, bg_est]
        try:
            popt, _ = curve_fit(self._gauss_plus_linear, channels, y, p0=p0, maxfev=5000)
            a, mu, sigma, m, b = popt
            if (abs(mu - center_guess) > (peak_hi - peak_lo) or
                    abs(sigma) > (peak_hi - peak_lo) or a < 0):
                return {"area": 0.0, "ok": False}
            area = a * abs(sigma) * np.sqrt(2 * np.pi)
            y_fit = self._gauss_plus_linear(channels, *popt)
            y_bg = m * channels + b
            return {"area": area, "amplitude": a, "center": mu, "sigma": abs(sigma),
                    "slope": m, "intercept": b, "channels": channels, "y_data": y,
                    "y_fit": y_fit, "y_bg": y_bg, "ok": True}
        except (RuntimeError, ValueError):
            return {"area": 0.0, "ok": False}

    def sum_roi(self, energy_idx, det, peak_lo, peak_hi, apply_cal=True):
        spectrum = self.get_spectrum(energy_idx, det, apply_cal=apply_cal)
        return float(np.sum(spectrum[peak_lo:peak_hi]))

    def batch_extract(self, bg_lo, bg_hi, peak_lo, peak_hi,
                      apply_cal=True, apply_dt=True, use_bkg=True,
                      progress_callback=None):
        results = np.zeros((self.n_points, self.n_elements))
        for ei in range(self.n_points):
            for det in range(self.n_elements):
                if use_bkg:
                    fit = self.fit_peak(ei, det, bg_lo, bg_hi, peak_lo, peak_hi,
                                        apply_cal=apply_cal)
                    area = fit["area"]
                else:
                    area = self.sum_roi(ei, det, peak_lo, peak_hi,
                                        apply_cal=apply_cal)
                if apply_dt:
                    area *= self.dt_factors[ei, det]
                results[ei, det] = area
            if progress_callback and (ei + 1) % 10 == 0:
                progress_callback(ei + 1, self.n_points)
        return results

    def get_spectrum(self, energy_idx, det, apply_cal=True):
        spectrum = self.spectra[energy_idx, det, :].astype(float)
        if not (apply_cal and self.calibrated):
            return spectrum
        scale = self.cal_scale[det]
        offset = self.cal_offset[det]
        if abs(scale - 1.0) < 1e-6 and abs(offset) < 0.01:
            return spectrum
        channels = np.arange(self.n_channels, dtype=float)
        raw_at_corrected = (channels - offset) / scale
        spectrum = np.interp(raw_at_corrected, channels, spectrum, left=0, right=0)
        return spectrum

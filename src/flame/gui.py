import os
import sys
import glob
from datetime import datetime
if sys.platform == "win32":
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("flame.xafs.processor")
import wx
import numpy as np
from larch import Group
from larch.io import create_athena
from larch.xafs import pre_edge
import matplotlib
matplotlib.use('WXAgg')
from wxmplot import PlotPanel

from flame import __version__ as FLAME_VERSION
from flame.hdfdata import HdfData


class XrfViewerPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        self.data = None

        main_sizer = wx.BoxSizer(wx.HORIZONTAL)

        left_scroll = wx.ScrolledWindow(self, style=wx.VSCROLL)
        left_scroll.SetScrollRate(0, 10)
        left = left_scroll
        left_sizer = wx.BoxSizer(wx.VERTICAL)

        load_btn = wx.Button(left, label="Load HDF File...")
        load_btn.Bind(wx.EVT_BUTTON, self.on_load)
        left_sizer.Add(load_btn, 0, wx.EXPAND | wx.ALL, 5)

        self.file_label = wx.StaticText(left, label="No file loaded")
        left_sizer.Add(self.file_label, 0, wx.ALL, 5)

        left_sizer.Add(wx.StaticLine(left), 0, wx.EXPAND | wx.ALL, 5)

        left_sizer.Add(wx.StaticText(left, label="Energy point:"), 0, wx.LEFT | wx.TOP, 5)
        self.energy_slider = wx.Slider(left, value=0, minValue=0, maxValue=1,
                                       style=wx.SL_HORIZONTAL | wx.SL_LABELS)
        self.energy_slider.Bind(wx.EVT_SLIDER, self.on_slider)
        left_sizer.Add(self.energy_slider, 0, wx.EXPAND | wx.ALL, 5)

        self.energy_text = wx.StaticText(left, label="E = --- eV (point 0/0)")
        left_sizer.Add(self.energy_text, 0, wx.LEFT, 5)

        quick_sizer = wx.BoxSizer(wx.HORIZONTAL)
        for label, pos in [("Start", "start"), ("Mid", "mid"), ("End", "end")]:
            btn = wx.Button(left, label=label, size=(60, -1))
            btn.Bind(wx.EVT_BUTTON, lambda evt, p=pos: self.on_quick_jump(p))
            quick_sizer.Add(btn, 0, wx.ALL, 2)
        left_sizer.Add(quick_sizer, 0, wx.ALIGN_CENTER | wx.BOTTOM, 5)

        left_sizer.Add(wx.StaticLine(left), 0, wx.EXPAND | wx.ALL, 5)

        left_sizer.Add(wx.StaticText(left, label="Detector elements (DT shown, not applied):"),
                        0, wx.LEFT | wx.TOP, 5)
        self.det_checklist = wx.CheckListBox(left,
                                             choices=["Element {}".format(i) for i in range(13)])
        self.det_checklist.SetCheckedItems([0])
        self.det_checklist.Bind(wx.EVT_CHECKLISTBOX, self.on_det_check)
        left_sizer.Add(self.det_checklist, 1, wx.EXPAND | wx.ALL, 5)

        det_btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_all = wx.Button(left, label="All", size=(50, -1))
        btn_none = wx.Button(left, label="None", size=(50, -1))
        btn_one = wx.Button(left, label="One", size=(50, -1))
        btn_all.Bind(wx.EVT_BUTTON, self.on_det_all)
        btn_none.Bind(wx.EVT_BUTTON, self.on_det_none)
        btn_one.Bind(wx.EVT_BUTTON, self.on_det_one)
        det_btn_sizer.Add(btn_all, 0, wx.ALL, 2)
        det_btn_sizer.Add(btn_none, 0, wx.ALL, 2)
        det_btn_sizer.Add(btn_one, 0, wx.ALL, 2)
        left_sizer.Add(det_btn_sizer, 0, wx.ALIGN_CENTER)

        left_sizer.Add(wx.StaticLine(left), 0, wx.EXPAND | wx.ALL, 5)

        left_sizer.Add(wx.StaticText(left, label="X-axis:"), 0, wx.LEFT | wx.TOP, 5)
        xlim_sizer = wx.BoxSizer(wx.HORIZONTAL)
        xlim_sizer.Add(wx.StaticText(left, label="Lo:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)
        self.xlo_ctrl = wx.SpinCtrl(left, value="0", min=0, max=4095, size=(70, -1))
        xlim_sizer.Add(self.xlo_ctrl, 0, wx.ALL, 2)
        xlim_sizer.Add(wx.StaticText(left, label="Hi:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)
        self.xhi_ctrl = wx.SpinCtrl(left, value="4096", min=1, max=4096, size=(70, -1))
        xlim_sizer.Add(self.xhi_ctrl, 0, wx.ALL, 2)
        apply_btn = wx.Button(left, label="Apply", size=(50, -1))
        apply_btn.Bind(wx.EVT_BUTTON, self.on_apply_xlim)
        xlim_sizer.Add(apply_btn, 0, wx.ALL, 2)
        reset_btn = wx.Button(left, label="Reset", size=(50, -1))
        reset_btn.Bind(wx.EVT_BUTTON, self.on_reset_xlim)
        xlim_sizer.Add(reset_btn, 0, wx.ALL, 2)
        left_sizer.Add(xlim_sizer, 0, wx.ALL, 2)

        self.log_check = wx.CheckBox(left, label="Log scale")
        self.log_check.Bind(wx.EVT_CHECKBOX, self.on_log_toggle)
        left_sizer.Add(self.log_check, 0, wx.ALL, 5)

        left_sizer.Add(wx.StaticLine(left), 0, wx.EXPAND | wx.ALL, 5)
        left_sizer.Add(wx.StaticText(left, label="Channel calibration (2-peak linear):"),
                        0, wx.LEFT | wx.TOP, 5)

        cal_ref_sizer = wx.BoxSizer(wx.HORIZONTAL)
        cal_ref_sizer.Add(wx.StaticText(left, label="Ref el:"), 0,
                          wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)
        self.cal_ref_ctrl = wx.SpinCtrl(left, value="0", min=0, max=12, size=(50, -1))
        cal_ref_sizer.Add(self.cal_ref_ctrl, 0, wx.ALL, 2)
        left_sizer.Add(cal_ref_sizer, 0, wx.ALL, 2)

        pk1_sizer = wx.BoxSizer(wx.HORIZONTAL)
        pk1_sizer.Add(wx.StaticText(left, label="Peak 1:"), 0,
                       wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)
        self.pk1_lo_ctrl = wx.SpinCtrl(left, value="0", min=0, max=4095, size=(65, -1))
        self.pk1_hi_ctrl = wx.SpinCtrl(left, value="0", min=0, max=4096, size=(65, -1))
        pk1_sizer.Add(self.pk1_lo_ctrl, 0, wx.ALL, 2)
        pk1_sizer.Add(wx.StaticText(left, label="-"), 0, wx.ALIGN_CENTER_VERTICAL)
        pk1_sizer.Add(self.pk1_hi_ctrl, 0, wx.ALL, 2)
        left_sizer.Add(pk1_sizer, 0, wx.LEFT, 5)

        pk2_sizer = wx.BoxSizer(wx.HORIZONTAL)
        pk2_sizer.Add(wx.StaticText(left, label="Peak 2:"), 0,
                       wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)
        self.pk2_lo_ctrl = wx.SpinCtrl(left, value="0", min=0, max=4095, size=(65, -1))
        self.pk2_hi_ctrl = wx.SpinCtrl(left, value="0", min=0, max=4096, size=(65, -1))
        pk2_sizer.Add(self.pk2_lo_ctrl, 0, wx.ALL, 2)
        pk2_sizer.Add(wx.StaticText(left, label="-"), 0, wx.ALIGN_CENTER_VERTICAL)
        pk2_sizer.Add(self.pk2_hi_ctrl, 0, wx.ALL, 2)
        left_sizer.Add(pk2_sizer, 0, wx.LEFT, 5)

        cal_btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        auto_btn = wx.Button(left, label="Auto-detect", size=(85, -1))
        auto_btn.Bind(wx.EVT_BUTTON, self.on_auto_peaks)
        cal_btn_sizer.Add(auto_btn, 0, wx.ALL, 2)
        cal_btn = wx.Button(left, label="Calibrate", size=(80, -1))
        cal_btn.Bind(wx.EVT_BUTTON, self.on_calibrate)
        cal_btn_sizer.Add(cal_btn, 0, wx.ALL, 2)
        self.cal_apply_check = wx.CheckBox(left, label="Apply cal")
        self.cal_apply_check.SetValue(False)
        self.cal_apply_check.Bind(wx.EVT_CHECKBOX, self.on_cal_toggle)
        cal_btn_sizer.Add(self.cal_apply_check, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)
        left_sizer.Add(cal_btn_sizer, 0, wx.ALL, 2)

        self.cal_status = wx.TextCtrl(left, style=wx.TE_MULTILINE | wx.TE_READONLY,
                                      size=(-1, 100))
        self.cal_status.SetFont(wx.Font(8, wx.FONTFAMILY_MODERN, wx.FONTSTYLE_NORMAL,
                                        wx.FONTWEIGHT_NORMAL))
        left_sizer.Add(self.cal_status, 0, wx.EXPAND | wx.ALL, 5)

        left_sizer.Add(wx.StaticLine(left), 0, wx.EXPAND | wx.ALL, 5)
        left_sizer.Add(wx.StaticText(left, label="Peak fitting:"), 0, wx.LEFT | wx.TOP, 5)

        bg_sizer = wx.BoxSizer(wx.HORIZONTAL)
        bg_sizer.Add(wx.StaticText(left, label="Bkg:"), 0,
                      wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)
        self.bg_lo_ctrl = wx.SpinCtrl(left, value="2000", min=0, max=4095, size=(65, -1))
        bg_sizer.Add(self.bg_lo_ctrl, 0, wx.ALL, 2)
        bg_sizer.Add(wx.StaticText(left, label="-"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.bg_hi_ctrl = wx.SpinCtrl(left, value="2250", min=1, max=4096, size=(65, -1))
        bg_sizer.Add(self.bg_hi_ctrl, 0, wx.ALL, 2)
        left_sizer.Add(bg_sizer, 0, wx.ALL, 2)

        roi_sizer = wx.BoxSizer(wx.HORIZONTAL)
        roi_sizer.Add(wx.StaticText(left, label="Peak:"), 0,
                       wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)
        self.roi_lo_ctrl = wx.SpinCtrl(left, value="2080", min=0, max=4095, size=(65, -1))
        roi_sizer.Add(self.roi_lo_ctrl, 0, wx.ALL, 2)
        roi_sizer.Add(wx.StaticText(left, label="-"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.roi_hi_ctrl = wx.SpinCtrl(left, value="2180", min=1, max=4096, size=(65, -1))
        roi_sizer.Add(self.roi_hi_ctrl, 0, wx.ALL, 2)
        left_sizer.Add(roi_sizer, 0, wx.ALL, 2)

        norm_roi_sizer = wx.BoxSizer(wx.HORIZONTAL)
        norm_roi_sizer.Add(wx.StaticText(left, label="Norm:"), 0,
                            wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)
        self.norm_lo_ctrl = wx.SpinCtrl(left, value="0", min=0, max=4095, size=(65, -1))
        norm_roi_sizer.Add(self.norm_lo_ctrl, 0, wx.ALL, 2)
        norm_roi_sizer.Add(wx.StaticText(left, label="-"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.norm_hi_ctrl = wx.SpinCtrl(left, value="0", min=0, max=4096, size=(65, -1))
        norm_roi_sizer.Add(self.norm_hi_ctrl, 0, wx.ALL, 2)
        left_sizer.Add(norm_roi_sizer, 0, wx.ALL, 2)

        norm_choice_sizer = wx.BoxSizer(wx.HORIZONTAL)
        norm_choice_sizer.Add(wx.StaticText(left, label="Divide by:"), 0,
                               wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)
        self.norm_combo = wx.ComboBox(left, style=wx.CB_READONLY,
                                      choices=["(no file loaded)"],
                                      size=(180, -1))
        self.norm_combo.SetSelection(0)
        norm_choice_sizer.Add(self.norm_combo, 1, wx.ALL, 2)
        left_sizer.Add(norm_choice_sizer, 0, wx.EXPAND | wx.ALL, 2)

        self.roi_show_check = wx.CheckBox(left, label="Show on spectrum")
        self.roi_show_check.SetValue(True)
        self.roi_show_check.Bind(wx.EVT_CHECKBOX, lambda e: self.update_plot(full=True))
        left_sizer.Add(self.roi_show_check, 0, wx.LEFT, 10)

        self.use_bkg_check = wx.CheckBox(left, label="Use background fit")
        self.use_bkg_check.SetValue(True)
        left_sizer.Add(self.use_bkg_check, 0, wx.LEFT, 10)

        fit_btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        fit_one_btn = wx.Button(left, label="Fit this point", size=(90, -1))
        fit_one_btn.Bind(wx.EVT_BUTTON, self.on_fit_one)
        fit_btn_sizer.Add(fit_one_btn, 0, wx.ALL, 2)
        batch_btn = wx.Button(left, label="Batch extract", size=(90, -1))
        batch_btn.Bind(wx.EVT_BUTTON, self.on_batch_extract)
        fit_btn_sizer.Add(batch_btn, 0, wx.ALL, 2)
        left_sizer.Add(fit_btn_sizer, 0, wx.ALL, 2)

        self.fit_status = wx.TextCtrl(left, style=wx.TE_MULTILINE | wx.TE_READONLY,
                                      size=(-1, 60))
        self.fit_status.SetFont(wx.Font(8, wx.FONTFAMILY_MODERN, wx.FONTSTYLE_NORMAL,
                                        wx.FONTWEIGHT_NORMAL))
        left_sizer.Add(self.fit_status, 0, wx.EXPAND | wx.ALL, 5)

        left_sizer.Add(wx.StaticLine(left), 0, wx.EXPAND | wx.ALL, 5)
        left_sizer.Add(wx.StaticText(left, label="Merge & Export (after batch):"),
                        0, wx.LEFT | wx.TOP, 5)

        self.merge_checklist = wx.CheckListBox(left,
                                                choices=["El {}".format(i) for i in range(13)])
        self.merge_checklist.SetCheckedItems(
            [i for i in range(13) if i not in (2, 12)])
        left_sizer.Add(self.merge_checklist, 1, wx.EXPAND | wx.ALL, 5)

        merge_btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        merge_all_btn = wx.Button(left, label="All", size=(40, -1))
        merge_none_btn = wx.Button(left, label="None", size=(40, -1))
        merge_auto_btn = wx.Button(left, label="Auto", size=(40, -1))
        merge_all_btn.Bind(wx.EVT_BUTTON, self.on_merge_all)
        merge_none_btn.Bind(wx.EVT_BUTTON, self.on_merge_none)
        merge_auto_btn.Bind(wx.EVT_BUTTON, self.on_merge_auto)
        merge_btn_sizer.Add(merge_all_btn, 0, wx.ALL, 2)
        merge_btn_sizer.Add(merge_none_btn, 0, wx.ALL, 2)
        merge_btn_sizer.Add(merge_auto_btn, 0, wx.ALL, 2)
        left_sizer.Add(merge_btn_sizer, 0, wx.ALIGN_CENTER)

        action_sizer = wx.BoxSizer(wx.HORIZONTAL)
        merge_plot_btn = wx.Button(left, label="Merge && Plot", size=(90, -1))
        merge_plot_btn.Bind(wx.EVT_BUTTON, self.on_merge_plot)
        action_sizer.Add(merge_plot_btn, 0, wx.ALL, 2)
        export_dat_btn = wx.Button(left, label="Export .dat", size=(80, -1))
        export_dat_btn.Bind(wx.EVT_BUTTON, self.on_export_dat)
        action_sizer.Add(export_dat_btn, 0, wx.ALL, 2)
        export_prj_btn = wx.Button(left, label="Export .prj", size=(80, -1))
        export_prj_btn.Bind(wx.EVT_BUTTON, self.on_export_prj)
        action_sizer.Add(export_prj_btn, 0, wx.ALL, 2)
        left_sizer.Add(action_sizer, 0, wx.ALL, 2)

        left_sizer.Add(wx.StaticLine(left), 0, wx.EXPAND | wx.ALL, 5)
        batch_all_btn = wx.Button(left, label="Batch Process All", size=(260, -1))
        batch_all_btn.Bind(wx.EVT_BUTTON, self.on_batch_all)
        left_sizer.Add(batch_all_btn, 0, wx.ALIGN_CENTER | wx.ALL, 5)

        left.SetSizer(left_sizer)

        right = wx.Panel(self)
        right_sizer = wx.BoxSizer(wx.VERTICAL)

        self.panel1 = PlotPanel(right, size=(700, 350), fontsize=8,
                                output_title="xrf_spectrum")
        self.panel1.conf.titlefontsize = 9
        self.panel1.conf.legendfontsize = 7
        self.panel1.conf.labelfontsize = 8
        self.panel1.SetMinSize((400, 250))
        right_sizer.Add(self.panel1, 1, wx.EXPAND)

        self.panel2 = PlotPanel(right, size=(700, 250), fontsize=8,
                                output_title="fit_result")
        self.panel2.conf.titlefontsize = 9
        self.panel2.conf.legendfontsize = 7
        self.panel2.conf.labelfontsize = 8
        self.panel2.SetMinSize((400, 200))
        right_sizer.Add(self.panel2, 1, wx.EXPAND)

        right.SetSizer(right_sizer)

        left_scroll.SetMinSize((340, -1))
        main_sizer.Add(left_scroll, 0, wx.EXPAND)
        main_sizer.Add(right, 1, wx.EXPAND)
        self.SetSizer(main_sizer)

        self.xlim = None
        self.use_log = False
        self.apply_cal = False
        self.batch_results = None
        self._last_norm = None
        self._last_norm_label = "IpreKB-count/value"
        self._plot1_checked = None
        self._plot1_initialized = False

    def on_load(self, event):
        dlg = wx.FileDialog(self, "Open HDF File", wildcard="HDF files (*.hdf)|*.hdf",
                            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            try:
                self.data = HdfData(path)
                self.file_label.SetLabel(self.data.basename)
                self.energy_slider.SetMax(self.data.n_points - 1)
                self.energy_slider.SetValue(0)
                choices = ["Element {} (ch {})".format(i, i + 1) for i in range(self.data.n_elements)]
                self.det_checklist.Set(choices)
                self.det_checklist.SetCheckedItems([0])
                self.xlim = None
                self.xlo_ctrl.SetValue(0)
                self.xhi_ctrl.SetValue(self.data.n_channels)
                self.apply_cal = False
                self.cal_apply_check.SetValue(False)
                self.cal_status.SetValue("")
                norm_choices = ["Norm ROI"] + list(self.data.scalar_signal_names)
                self.norm_combo.Set(norm_choices)
                self.norm_combo.SetSelection(0)
                self.update_energy_label()
                self.update_plot(full=True)
            except Exception as e:
                wx.MessageBox("Error loading file:\n{}".format(e), "Error",
                              wx.OK | wx.ICON_ERROR)
        dlg.Destroy()

    def on_slider(self, event):
        self.update_energy_label()
        self.update_plot()

    def on_quick_jump(self, pos):
        if self.data is None:
            return
        if pos == "start":
            self.energy_slider.SetValue(0)
        elif pos == "mid":
            self.energy_slider.SetValue(self.data.n_points // 2)
        elif pos == "end":
            self.energy_slider.SetValue(self.data.n_points - 1)
        self.update_energy_label()
        self.update_plot()

    def on_det_check(self, event):
        self.update_plot(full=True)

    def on_det_all(self, event):
        if self.data:
            self.det_checklist.SetCheckedItems(range(self.data.n_elements))
            self.update_plot(full=True)

    def on_det_none(self, event):
        self.det_checklist.SetCheckedItems([])
        self.update_plot(full=True)

    def on_det_one(self, event):
        sel = self.det_checklist.GetSelection()
        if sel == wx.NOT_FOUND:
            sel = 0
        self.det_checklist.SetCheckedItems([sel])
        self.update_plot(full=True)

    def on_apply_xlim(self, event):
        lo = self.xlo_ctrl.GetValue()
        hi = self.xhi_ctrl.GetValue()
        if lo < hi:
            self.xlim = (lo, hi)
            self.update_plot(full=True)

    def on_reset_xlim(self, event):
        self.xlim = None
        if self.data:
            self.xlo_ctrl.SetValue(0)
            self.xhi_ctrl.SetValue(self.data.n_channels)
        self.update_plot(full=True)

    def on_log_toggle(self, event):
        self.use_log = self.log_check.GetValue()
        self.update_plot(full=True)

    def on_auto_peaks(self, event):
        if self.data is None:
            return
        ref_el = self.cal_ref_ctrl.GetValue()
        ref_spectrum = self.data.spectra[-1, ref_el, :].astype(float)
        auto_peaks = HdfData._find_peaks_auto(ref_spectrum)
        if len(auto_peaks) < 2:
            self.cal_status.SetValue("Auto-detect found fewer than 2 peaks")
            return
        sep = []
        for i in range(len(auto_peaks)):
            for j in range(i + 1, len(auto_peaks)):
                sep.append((abs(auto_peaks[i] - auto_peaks[j]), i, j))
        sep.sort(reverse=True)
        p1, p2 = sorted([auto_peaks[sep[0][1]], auto_peaks[sep[0][2]]])
        hw = 30
        self.pk1_lo_ctrl.SetValue(max(0, int(p1) - hw))
        self.pk1_hi_ctrl.SetValue(min(self.data.n_channels, int(p1) + hw))
        self.pk2_lo_ctrl.SetValue(max(0, int(p2) - hw))
        self.pk2_hi_ctrl.SetValue(min(self.data.n_channels, int(p2) + hw))
        lines = ["Auto-detected {} peaks in el {}".format(len(auto_peaks), ref_el)]
        lines.append("Selected: ch ~{} and ch ~{}".format(int(p1), int(p2)))
        lines.append("Separation: {} channels".format(abs(int(p2) - int(p1))))
        self.cal_status.SetValue("\n".join(lines))

    def on_calibrate(self, event):
        if self.data is None:
            return
        ref_el = self.cal_ref_ctrl.GetValue()
        p1_lo = self.pk1_lo_ctrl.GetValue()
        p1_hi = self.pk1_hi_ctrl.GetValue()
        p2_lo = self.pk2_lo_ctrl.GetValue()
        p2_hi = self.pk2_hi_ctrl.GetValue()
        if p1_lo == 0 and p1_hi == 0 and p2_lo == 0 and p2_hi == 0:
            pk1 = None
            pk2 = None
        else:
            pk1 = (p1_lo, p1_hi)
            pk2 = (p2_lo, p2_hi)
        results, msg = self.data.calibrate_linear(ref_element=ref_el,
                                                   peak1_range=pk1, peak2_range=pk2)
        if results is None:
            self.cal_status.SetValue("Calibration failed: {}".format(msg))
            return
        if self.data.cal_peaks:
            pk1r, pk2r, rc1, rc2 = self.data.cal_peaks
            self.pk1_lo_ctrl.SetValue(pk1r[0])
            self.pk1_hi_ctrl.SetValue(pk1r[1])
            self.pk2_lo_ctrl.SetValue(pk2r[0])
            self.pk2_hi_ctrl.SetValue(pk2r[1])
        lines = ["Ref el {}: pk1={:.1f}, pk2={:.1f}".format(ref_el, rc1, rc2)]
        lines.append("{:<5s} {:>8s} {:>8s} {:>8s} {:>8s}".format(
            "El", "scale", "offset", "pk1", "pk2"))
        for det, scale, offset, c1, c2, ok in results:
            if not ok:
                lines.append("{:<5d} {:>8s}".format(det, "FAILED"))
            else:
                flag = " ***" if abs(scale - 1.0) > 0.005 or abs(offset) > 5 else ""
                lines.append("{:<5d} {:>8.5f} {:>+8.2f} {:>8.1f} {:>8.1f}{}".format(
                    det, scale, offset, c1, c2, flag))
        self.cal_status.SetValue("\n".join(lines))
        self.cal_apply_check.SetValue(True)
        self.apply_cal = True
        self.update_plot(full=True)

    def on_cal_toggle(self, event):
        self.apply_cal = self.cal_apply_check.GetValue()
        self.update_plot(full=True)

    def on_fit_one(self, event):
        if self.data is None:
            return
        bg_lo = self.bg_lo_ctrl.GetValue()
        bg_hi = self.bg_hi_ctrl.GetValue()
        peak_lo = self.roi_lo_ctrl.GetValue()
        peak_hi = self.roi_hi_ctrl.GetValue()
        use_bkg = self.use_bkg_check.GetValue()
        if peak_lo >= peak_hi:
            return
        if use_bkg:
            if bg_lo >= bg_hi:
                return
            if peak_lo < bg_lo or peak_hi > bg_hi:
                self.fit_status.SetValue("Error: Peak window must be inside Bkg window")
                return
        idx = self.energy_slider.GetValue()
        use_cal = self.apply_cal and self.data.calibrated
        checked = self.det_checklist.GetCheckedItems()
        if not checked:
            checked = [0]

        colors = matplotlib.colormaps["tab20"]
        lines = []
        ax2 = self.panel2.axes

        if use_bkg:
            title = "Gaussian fit — E={:.1f} eV (point {})".format(
                self.data.energies[idx], idx)
            first = True
            fit_annotations = []
            for det in checked:
                fit = self.data.fit_peak(idx, det, bg_lo, bg_hi, peak_lo, peak_hi,
                                         apply_cal=use_cal)
                c = colors(det / max(self.data.n_elements - 1, 1))
                color_hex = matplotlib.colors.to_hex(c)
                if fit["ok"]:
                    if first:
                        self.panel2.plot(fit["channels"], fit["y_data"],
                                        marker="o", markersize=3, linewidth=0,
                                        style='solid', color=color_hex, alpha=0.5,
                                        xlabel="Channel", ylabel="Counts",
                                        title=title, show_legend=False,
                                        label="_nolegend_", delay_draw=True)
                        first = False
                    else:
                        self.panel2.oplot(fit["channels"], fit["y_data"],
                                         marker="o", markersize=3, linewidth=0,
                                         style='solid', color=color_hex, alpha=0.5,
                                         label="_nolegend_", delay_draw=True)
                    self.panel2.oplot(fit["channels"], fit["y_fit"],
                                     linewidth=1.5, color=color_hex,
                                     style='solid', marker='None',
                                     label="_nolegend_", delay_draw=True)
                    ax2.plot(fit["channels"], fit["y_bg"], linestyle="--",
                             linewidth=0.8, color=c, alpha=0.5)
                    peak_ch = fit["channels"]
                    peak_mask = (peak_ch >= peak_lo) & (peak_ch <= peak_hi)
                    ax2.fill_between(peak_ch[peak_mask],
                                     fit["y_bg"][peak_mask],
                                     fit["y_fit"][peak_mask],
                                     alpha=0.2, color=c)
                    fit_annotations.append((fit["center"], fit["amplitude"],
                                            det, fit["area"], c))
                    lines.append("El {:>2d}: area={:.0f} ctr={:.1f} sig={:.1f}".format(
                        det, fit["area"], fit["center"], fit["sigma"]))
                else:
                    lines.append("El {:>2d}: fit failed".format(det))
            if first:
                self.panel2.plot([peak_lo, peak_hi], [0, 0],
                                xlabel="Channel", ylabel="Counts",
                                title=title, style='solid', marker='None',
                                delay_draw=True)
            ax2.axvspan(peak_lo, peak_hi, alpha=0.08, color="green")
            for i, (ctr, amp, det, area, clr) in enumerate(fit_annotations):
                ax2.annotate("El{} {:.0f}".format(det, area),
                             xy=(ctr, amp), fontsize=6, color=clr,
                             textcoords="offset points", xytext=(4, 3 + i * 10),
                             ha="left", va="bottom")
        else:
            title = "ROI sum — E={:.1f} eV (point {})".format(
                self.data.energies[idx], idx)
            first = True
            for det in checked:
                spectrum = self.data.get_spectrum(idx, det, apply_cal=use_cal)
                channels = np.arange(peak_lo, peak_hi, dtype=float)
                y = spectrum[peak_lo:peak_hi].astype(float)
                roi_sum = float(np.sum(y))
                c = colors(det / max(self.data.n_elements - 1, 1))
                color_hex = matplotlib.colors.to_hex(c)
                if first:
                    self.panel2.plot(channels, y,
                                    linewidth=0.8, color=color_hex,
                                    style='solid', marker='None',
                                    xlabel="Channel", ylabel="Counts",
                                    title=title, show_legend=False,
                                    label="_nolegend_", delay_draw=True)
                    first = False
                else:
                    self.panel2.oplot(channels, y,
                                     linewidth=0.8, color=color_hex,
                                     style='solid', marker='None',
                                     label="_nolegend_", delay_draw=True)
                ax2.fill_between(channels, 0, y, alpha=0.15, color=c)
                lines.append("El {:>2d}: sum={:.0f}".format(det, roi_sum))
            if first:
                self.panel2.plot([peak_lo, peak_hi], [0, 0],
                                xlabel="Channel", ylabel="Counts",
                                title=title, style='solid', marker='None',
                                delay_draw=True)
            ax2.axvspan(peak_lo, peak_hi, alpha=0.08, color="green")

        self.panel2.draw()
        self.fit_status.SetValue("\n".join(lines))

    def on_batch_extract(self, event):
        if self.data is None:
            return
        bg_lo = self.bg_lo_ctrl.GetValue()
        bg_hi = self.bg_hi_ctrl.GetValue()
        peak_lo = self.roi_lo_ctrl.GetValue()
        peak_hi = self.roi_hi_ctrl.GetValue()
        use_bkg = self.use_bkg_check.GetValue()
        if peak_lo >= peak_hi:
            return
        if use_bkg:
            if bg_lo >= bg_hi:
                return
            if peak_lo < bg_lo or peak_hi > bg_hi:
                self.fit_status.SetValue("Error: Peak window must be inside Bkg window")
                return
        use_cal = self.apply_cal and self.data.calibrated

        msg = "Fitting peaks across all energy points..." if use_bkg else \
              "Summing ROI across all energy points..."
        dlg = wx.ProgressDialog("Batch extraction", msg,
                                maximum=self.data.n_points,
                                parent=self.GetParent(),
                                style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE |
                                      wx.PD_ELAPSED_TIME | wx.PD_REMAINING_TIME)

        def progress(done, total):
            dlg.Update(done, "Processing {}/{}...".format(done, total))

        self.batch_results = self.data.batch_extract(
            bg_lo, bg_hi, peak_lo, peak_hi,
            apply_cal=use_cal, apply_dt=True, use_bkg=use_bkg,
            progress_callback=progress)
        dlg.Destroy()

        self._auto_flag_elements()

        norm, norm_label = self._get_norm_signal()
        self._last_norm = norm
        self._last_norm_label = norm_label

        checked = self.det_checklist.GetCheckedItems()
        if not checked:
            checked = range(self.data.n_elements)

        colors = matplotlib.colormaps["tab20"]
        energies = self.data.energies
        method = "Bkg {}-{}, ".format(bg_lo, bg_hi) if use_bkg else "ROI sum, "
        title = "Extracted mu(E) — {}Peak {}-{} (DT corrected)".format(
            method, peak_lo, peak_hi)
        ylabel = "Counts / {}".format(norm_label)

        first = True
        for det in checked:
            mu = self.batch_results[:, det] / norm
            c = colors(det / max(self.data.n_elements - 1, 1))
            color_hex = matplotlib.colors.to_hex(c)
            if first:
                self.panel2.plot(energies, mu, linewidth=0.8,
                                color=color_hex, label="El {}".format(det),
                                style='solid', marker='None',
                                xlabel="Energy (eV)", ylabel=ylabel,
                                title=title, show_legend=False,
                                delay_draw=True)
                first = False
            else:
                self.panel2.oplot(energies, mu, linewidth=0.8,
                                 color=color_hex, label="El {}".format(det),
                                 style='solid', marker='None',
                                 delay_draw=True)
        if first:
            self.panel2.plot([0], [0], xlabel="Energy (eV)", ylabel=ylabel,
                            title=title, style='solid', marker='None',
                            delay_draw=True)
        self.panel2.draw()
        method_label = "bkg fit" if use_bkg else "ROI sum"
        self.fit_status.SetValue("Batch done: {} pts x {} elements\n"
                                 "Method: {}, Peak: {}-{}\n"
                                 "DT corrected, norm={}, cal={}".format(
                                     self.data.n_points, self.data.n_elements,
                                     method_label, peak_lo, peak_hi,
                                     norm_label,
                                     "yes" if use_cal else "no"))

    def _get_norm_signal(self):
        selection = self.norm_combo.GetStringSelection()
        if selection == "Norm ROI":
            norm_lo = self.norm_lo_ctrl.GetValue()
            norm_hi = self.norm_hi_ctrl.GetValue()
            if norm_lo < norm_hi and self.data is not None:
                use_cal = self.apply_cal and self.data.calibrated
                norm = np.zeros(self.data.n_points)
                for ei in range(self.data.n_points):
                    total = 0.0
                    for det in range(self.data.n_elements):
                        spec = self.data.get_spectrum(ei, det, apply_cal=use_cal)
                        total += np.sum(spec[norm_lo:norm_hi])
                    norm[ei] = total
                norm[norm == 0] = 1.0
                return norm, "NormROI {}-{}".format(norm_lo, norm_hi)
            return self.data.iprekb.copy(), "IpreKB-count/value"
        if selection and selection in self.data.scalar_signals:
            norm = self.data.get_scalar_signal(selection).copy()
            norm[norm == 0] = 1.0
            return norm, selection
        return self.data.iprekb.copy(), "IpreKB-count/value"

    def _auto_flag_elements(self):
        if self.batch_results is None or self.data is None:
            return
        norm, _ = self._get_norm_signal()
        labels = []
        all_els = list(range(self.data.n_elements))
        for det in all_els:
            mu = self.batch_results[:, det] / norm
            g = Group(energy=self.data.energies, mu=mu)
            try:
                pre_edge(g)
                labels.append("El {} e0={:.1f}".format(det, g.e0))
            except Exception:
                labels.append("El {} [ERR]".format(det))
        self.merge_checklist.Set(labels)
        self.merge_checklist.SetCheckedItems(all_els)

    def on_merge_all(self, event):
        self.merge_checklist.SetCheckedItems(range(self.merge_checklist.GetCount()))

    def on_merge_none(self, event):
        self.merge_checklist.SetCheckedItems([])

    def on_merge_auto(self, event):
        self._auto_flag_elements()

    def _get_short_name(self):
        base = os.path.splitext(self.data.basename)[0]
        parts = base.split("-")
        if len(parts) >= 2:
            return "{} ({})".format(parts[1], parts[-1])
        return base

    def _get_merge_label(self):
        base = os.path.splitext(self.data.basename)[0]
        parts = base.split("-")
        if len(parts) >= 2:
            return "{}_{}".format(parts[1], parts[-1])
        return base

    def on_merge_plot(self, event):
        if self.batch_results is None or self.data is None:
            self.fit_status.SetValue("Run batch extract first")
            return
        checked = list(self.merge_checklist.GetCheckedItems())
        if not checked:
            self.fit_status.SetValue("No elements selected for merge")
            return
        norm, norm_label = self._get_norm_signal()
        energies = self.data.energies
        mus = [self.batch_results[:, det] / norm for det in checked]
        mu_merged = np.mean(mus, axis=0)

        colors = matplotlib.colormaps["tab20"]
        title = "Merged mu(E) - {} elements".format(len(checked))
        ylabel = "Counts / {}".format(norm_label)

        first = True
        for det in checked:
            mu = self.batch_results[:, det] / norm
            c = colors(det / max(self.data.n_elements - 1, 1))
            color_hex = matplotlib.colors.to_hex(c)
            if first:
                self.panel2.plot(energies, mu, linewidth=0.5, alpha=0.4,
                                color=color_hex, label="_nolegend_",
                                style='solid', marker='None',
                                xlabel="Energy (eV)", ylabel=ylabel,
                                title=title, show_legend=False,
                                delay_draw=True)
                first = False
            else:
                self.panel2.oplot(energies, mu, linewidth=0.5, alpha=0.4,
                                 color=color_hex, label="_nolegend_",
                                 style='solid', marker='None',
                                 delay_draw=True)
        self.panel2.oplot(energies, mu_merged, linewidth=1.5, color="black",
                          label="Merge ({} els)".format(len(checked)),
                          style='solid', marker='None',
                          delay_draw=True)
        self.panel2.draw()
        self.fit_status.SetValue("Merged {} elements: {}".format(
            len(checked), checked))

    def _build_dat_header(self, checked_list, norm_label):
        n_el = self.data.n_elements
        h = []
        h.append("FLAME version: {}".format(FLAME_VERSION))
        h.append("Date: {}".format(datetime.now().strftime("%Y-%m-%dT%H:%M:%S")))
        h.append("Source: {}".format(self.data.basename))
        h.append("Energy points: {}".format(self.data.n_points))
        h.append("Detector elements: {}".format(n_el))
        h.append("Channels: {}".format(self.data.n_channels))
        h.append("")
        use_cal = self.apply_cal and self.data.calibrated
        h.append("Calibration applied: {}".format("yes" if use_cal else "no"))
        if self.data.calibrated and self.data.cal_peaks:
            pk1r, pk2r, rc1, rc2 = self.data.cal_peaks
            h.append("Calibration ref element: {}".format(
                self.cal_ref_ctrl.GetValue()))
            h.append("Calibration peak1 range: {}-{}".format(pk1r[0], pk1r[1]))
            h.append("Calibration peak2 range: {}-{}".format(pk2r[0], pk2r[1]))
            h.append("Calibration ref peak1 center: {:.2f}".format(rc1))
            h.append("Calibration ref peak2 center: {:.2f}".format(rc2))
            for det in range(n_el):
                s = self.data.cal_scale[det]
                o = self.data.cal_offset[det]
                h.append("Calibration el {:>2d}: scale={:.5f} offset={:+.2f}".format(
                    det, s, o))
        h.append("")
        bg_lo = self.bg_lo_ctrl.GetValue()
        bg_hi = self.bg_hi_ctrl.GetValue()
        peak_lo = self.roi_lo_ctrl.GetValue()
        peak_hi = self.roi_hi_ctrl.GetValue()
        use_bkg = self.use_bkg_check.GetValue()
        h.append("Extraction method: {}".format("background fit" if use_bkg else "ROI sum"))
        if use_bkg:
            h.append("Background window: {}-{}".format(bg_lo, bg_hi))
        h.append("Peak window: {}-{}".format(peak_lo, peak_hi))
        norm_lo = self.norm_lo_ctrl.GetValue()
        norm_hi = self.norm_hi_ctrl.GetValue()
        if norm_lo < norm_hi:
            h.append("Norm ROI window: {}-{}".format(norm_lo, norm_hi))
        h.append("Normalization: {}".format(norm_label))
        h.append("Deadtime correction: applied")
        h.append("")
        h.append("Merged elements: {}".format(checked_list))
        h.append("Excluded elements: {}".format(
            [i for i in range(n_el) if i not in checked_list]))
        h.append("")
        h.append("DT range per element:")
        for det in range(n_el):
            dt_min = self.data.dt_factors[:, det].min()
            dt_max = self.data.dt_factors[:, det].max()
            h.append("  el {:>2d}: {:.4f} - {:.4f}".format(det, dt_min, dt_max))
        h.append("")
        norm_col_name = norm_label.split("/")[0] if "/" in norm_label else norm_label
        col_header = "energy  {}".format(norm_col_name)
        for i in range(n_el):
            col_header += "  Ge_el{}".format(i)
        col_header += "  merged"
        h.append(col_header)
        return "\n".join(h)

    def on_export_dat(self, event):
        if self.batch_results is None or self.data is None:
            return
        default_name = self._get_merge_label() + "_peak.dat"
        dlg = wx.FileDialog(self, "Save .dat file", defaultFile=default_name,
                            wildcard="DAT files (*.dat)|*.dat",
                            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            checked = self.merge_checklist.GetCheckedItems()
            energies = self.data.energies
            n_el = self.data.n_elements

            checked_list = list(checked)
            norm, norm_label = self._get_norm_signal()
            merge_mus = [self.batch_results[:, det] / norm for det in checked_list]
            mu_merged = np.mean(merge_mus, axis=0) if merge_mus else np.zeros(len(energies))
            merge_counts = mu_merged * norm

            results = np.zeros((len(energies), n_el + 3))
            results[:, 0] = energies
            results[:, 1] = norm
            for det in range(n_el):
                results[:, det + 2] = self.batch_results[:, det]
            results[:, n_el + 2] = merge_counts

            header = self._build_dat_header(checked_list, norm_label)
            np.savetxt(path, results, header=header, fmt="%.6f", comments="# ")
            self.fit_status.SetValue("Saved {}".format(os.path.basename(path)))
        dlg.Destroy()

    def on_export_prj(self, event):
        if self.batch_results is None or self.data is None:
            return
        default_name = self._get_merge_label() + "_peak.prj"
        dlg = wx.FileDialog(self, "Save .prj file", defaultFile=default_name,
                            wildcard="Athena project (*.prj)|*.prj",
                            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            checked = set(self.merge_checklist.GetCheckedItems())
            energies = self.data.energies
            prefix = self._get_merge_label()

            norm, norm_label = self._get_norm_signal()

            prj = create_athena(path)
            merge_mus = []
            skipped = []
            for det in range(self.data.n_elements):
                mu = self.batch_results[:, det] / norm
                label = "{}_el{}".format(prefix, det)
                g = Group(energy=energies, mu=mu)
                g.filename = label
                g.label = label
                try:
                    pre_edge(g)
                    prj.add_group(g)
                    if det in checked:
                        merge_mus.append(mu)
                except Exception:
                    skipped.append(det)

            if merge_mus:
                mu_merged = np.mean(merge_mus, axis=0)
                merge_label = "{}_merge".format(prefix)
                gm = Group(energy=energies, mu=mu_merged)
                gm.filename = merge_label
                gm.label = merge_label
                try:
                    pre_edge(gm)
                except Exception:
                    pass
                prj.add_group(gm)

            prj.save()
            msg = "Saved {} ({} els + merge)".format(
                os.path.basename(path), self.data.n_elements - len(skipped))
            if skipped:
                msg += "\nSkipped els {} (pre_edge failed)".format(skipped)
            self.fit_status.SetValue(msg)
        dlg.Destroy()

    def _get_sample_name(self):
        base = os.path.splitext(self.data.basename)[0]
        parts = base.split("-")
        if len(parts) >= 2:
            return parts[1]
        return base

    def on_batch_all(self, event):
        if self.data is None:
            wx.MessageBox("Load an HDF file and configure parameters first.",
                          "No data", wx.OK | wx.ICON_WARNING)
            return

        bg_lo = self.bg_lo_ctrl.GetValue()
        bg_hi = self.bg_hi_ctrl.GetValue()
        peak_lo = self.roi_lo_ctrl.GetValue()
        peak_hi = self.roi_hi_ctrl.GetValue()
        use_bkg = self.use_bkg_check.GetValue()
        if peak_lo >= peak_hi:
            wx.MessageBox("Set a valid Peak window first.",
                          "Invalid parameters", wx.OK | wx.ICON_WARNING)
            return
        if use_bkg:
            if bg_lo >= bg_hi:
                wx.MessageBox("Set a valid Background window first.",
                              "Invalid parameters", wx.OK | wx.ICON_WARNING)
                return
            if peak_lo < bg_lo or peak_hi > bg_hi:
                wx.MessageBox("Peak window must be inside Background window.",
                              "Invalid parameters", wx.OK | wx.ICON_WARNING)
                return

        sample = self._get_sample_name()
        hdf_dir = os.path.dirname(self.data.filepath)
        pattern = os.path.join(hdf_dir, "*-{}-*.hdf".format(sample))
        all_files = sorted(glob.glob(pattern))
        if not all_files:
            wx.MessageBox("No HDF files matching sample '{}' found.".format(sample),
                          "No files", wx.OK | wx.ICON_WARNING)
            return

        file_names = [os.path.basename(f) for f in all_files]
        dlg = wx.MultiChoiceDialog(self.GetParent(),
                                   "Select HDF files to process for sample '{}'.\n"
                                   "Parameters from current session will be applied "
                                   "to each file.".format(sample),
                                   "Batch Process — {} files found".format(len(all_files)),
                                   file_names)
        dlg.SetSelections(range(len(all_files)))
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        selected_indices = dlg.GetSelections()
        dlg.Destroy()
        if not selected_indices:
            return

        selected_files = [all_files[i] for i in selected_indices]

        cal_ref = self.cal_ref_ctrl.GetValue()
        pk1_lo = self.pk1_lo_ctrl.GetValue()
        pk1_hi = self.pk1_hi_ctrl.GetValue()
        pk2_lo = self.pk2_lo_ctrl.GetValue()
        pk2_hi = self.pk2_hi_ctrl.GetValue()
        do_cal = self.apply_cal
        if pk1_lo == 0 and pk1_hi == 0 and pk2_lo == 0 and pk2_hi == 0:
            pk1_range = None
            pk2_range = None
        else:
            pk1_range = (pk1_lo, pk1_hi)
            pk2_range = (pk2_lo, pk2_hi)

        norm_selection = self.norm_combo.GetStringSelection()
        norm_lo = self.norm_lo_ctrl.GetValue()
        norm_hi = self.norm_hi_ctrl.GetValue()
        checked_els = list(self.merge_checklist.GetCheckedItems())

        progress = wx.ProgressDialog(
            "Batch Processing",
            "Starting...",
            maximum=len(selected_files),
            parent=self.GetParent(),
            style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE |
                  wx.PD_ELAPSED_TIME | wx.PD_REMAINING_TIME | wx.PD_CAN_ABORT)

        saved_data = self.data
        results_summary = []
        n_ok = 0
        n_fail = 0

        for file_idx, filepath in enumerate(selected_files):
            basename = os.path.basename(filepath)
            cont, _ = progress.Update(file_idx,
                                      "Processing {}/{}: {}".format(
                                          file_idx + 1, len(selected_files), basename))
            if not cont:
                break

            try:
                data = HdfData(filepath)
                self.data = data

                if do_cal:
                    cal_result, cal_msg = data.calibrate_linear(
                        ref_element=cal_ref,
                        peak1_range=pk1_range,
                        peak2_range=pk2_range)
                    if cal_result is None:
                        results_summary.append("{}: cal failed ({})".format(
                            basename, cal_msg))
                        n_fail += 1
                        continue

                use_cal = do_cal and data.calibrated
                batch = data.batch_extract(
                    bg_lo, bg_hi, peak_lo, peak_hi,
                    apply_cal=use_cal, apply_dt=True, use_bkg=use_bkg)
                self.batch_results = batch

                if norm_selection == "Norm ROI":
                    if norm_lo < norm_hi:
                        norm = np.zeros(data.n_points)
                        for ei in range(data.n_points):
                            total = 0.0
                            for det in range(data.n_elements):
                                spec = data.get_spectrum(ei, det, apply_cal=use_cal)
                                total += np.sum(spec[norm_lo:norm_hi])
                            norm[ei] = total
                        norm[norm == 0] = 1.0
                        norm_label = "NormROI {}-{}".format(norm_lo, norm_hi)
                    else:
                        norm = data.iprekb.copy()
                        norm_label = "IpreKB-count/value"
                elif norm_selection in data.scalar_signals:
                    norm = data.get_scalar_signal(norm_selection).copy()
                    norm[norm == 0] = 1.0
                    norm_label = norm_selection
                else:
                    norm = data.iprekb.copy()
                    norm_label = "IpreKB-count/value"

                merge_els = [el for el in checked_els if el < data.n_elements]
                if not merge_els:
                    merge_els = list(range(data.n_elements))

                merge_mus = [batch[:, det] / norm for det in merge_els]
                mu_merged = np.mean(merge_mus, axis=0)
                merge_counts = mu_merged * norm

                n_el = data.n_elements
                out = np.zeros((len(data.energies), n_el + 3))
                out[:, 0] = data.energies
                out[:, 1] = norm
                for det in range(n_el):
                    out[:, det + 2] = batch[:, det]
                out[:, n_el + 2] = merge_counts

                header = self._build_dat_header(merge_els, norm_label)

                base = os.path.splitext(basename)[0]
                parts = base.split("-")
                if len(parts) >= 2:
                    out_name = "{}_{}".format(parts[1], parts[-1])
                else:
                    out_name = base
                out_path = os.path.join(hdf_dir, out_name + "_peak.dat")
                np.savetxt(out_path, out, header=header, fmt="%.6f", comments="# ")

                results_summary.append("{}: OK -> {}".format(
                    basename, os.path.basename(out_path)))
                n_ok += 1

            except Exception as e:
                results_summary.append("{}: ERROR ({})".format(basename, e))
                n_fail += 1

        self.data = saved_data
        self.batch_results = None
        progress.Destroy()

        summary = "Batch complete: {} OK, {} failed\n\n".format(n_ok, n_fail)
        summary += "\n".join(results_summary)
        self.fit_status.SetValue(summary)

        if len(results_summary) > 5:
            wx.MessageBox(summary, "Batch Results",
                          wx.OK | wx.ICON_INFORMATION)

    def update_energy_label(self):
        if self.data is None:
            self.energy_text.SetLabel("E = --- eV (point 0/0)")
            return
        idx = self.energy_slider.GetValue()
        e = self.data.energies[idx]
        self.energy_text.SetLabel("E = {:.1f} eV (point {}/{})".format(
            e, idx + 1, self.data.n_points))

    def update_plot(self, full=False):
        if self.data is None:
            self.panel1.plot([0], [0], xlabel="Channel", ylabel="Counts",
                            title="No data loaded")
            self._plot1_initialized = False
            return

        idx = self.energy_slider.GetValue()
        energy = self.data.energies[idx]
        checked = tuple(self.det_checklist.GetCheckedItems())
        use_cal = self.apply_cal and self.data.calibrated

        if (self._plot1_initialized and not full
                and checked == self._plot1_checked and checked):
            for trace_idx, det in enumerate(checked):
                spectrum = self.data.get_spectrum(idx, det, apply_cal=use_cal)
                channels = np.arange(len(spectrum), dtype=float)
                lbl = "El{} DT={:.3f}".format(det, self.data.dt_factors[idx, det])
                self.panel1.update_line(trace_idx, channels, spectrum, draw=False)
                self.panel1.conf.traces[trace_idx].label = lbl
            cal_tag = " [CAL]" if use_cal else ""
            self.panel1.set_title("{} — E={:.1f} eV (pt {}){}".format(
                self._get_short_name(), energy, idx, cal_tag), delay_draw=True)
            self.panel1.conf.draw_legend(delay_draw=True)
            ax = self.panel1.axes
            if self.xlim:
                ax.set_xlim(self.xlim[0], self.xlim[1])
            else:
                ax.autoscale(axis='x')
            ax.set_yscale('log' if self.use_log else 'linear')
            if self.use_log:
                ax.set_ylim(bottom=1)
            else:
                ax.autoscale(axis='y')
            self.panel1.canvas.draw()
            return

        cal_tag = " [CAL]" if use_cal else ""
        title = "{} — E={:.1f} eV (pt {}){}".format(
            self._get_short_name(), energy, idx, cal_tag)

        xmin = self.xlim[0] if self.xlim else None
        xmax = self.xlim[1] if self.xlim else None
        ylog = self.use_log
        ymin = 1 if ylog else None

        colors = matplotlib.colormaps["tab20"]
        first = True
        for det in checked:
            spectrum = self.data.get_spectrum(idx, det, apply_cal=use_cal)
            channels = np.arange(len(spectrum), dtype=float)
            c = colors(det / max(self.data.n_elements - 1, 1))
            lbl = "El{} DT={:.3f}".format(det, self.data.dt_factors[idx, det])
            color_hex = matplotlib.colors.to_hex(c)
            if first:
                self.panel1.plot(channels, spectrum, linewidth=0.7,
                                color=color_hex, label=lbl,
                                xlabel="Channel", ylabel="Counts",
                                title=title, show_legend=True,
                                legend_loc="upper right",
                                ylog_scale=ylog,
                                xmin=xmin, xmax=xmax, ymin=ymin,
                                delay_draw=True)
                first = False
            else:
                self.panel1.oplot(channels, spectrum, linewidth=0.7,
                                 color=color_hex, label=lbl,
                                 delay_draw=True)

        if first:
            self.panel1.plot([0], [0], xlabel="Channel", ylabel="Counts",
                            title=title, delay_draw=True)

        if self.roi_show_check.GetValue():
            ax = self.panel1.axes
            bg_lo = self.bg_lo_ctrl.GetValue()
            bg_hi = self.bg_hi_ctrl.GetValue()
            roi_lo = self.roi_lo_ctrl.GetValue()
            roi_hi = self.roi_hi_ctrl.GetValue()
            if bg_lo < bg_hi:
                ax.axvspan(bg_lo, bg_hi, alpha=0.08, color="blue",
                           label="Bkg {}-{}".format(bg_lo, bg_hi))
            if roi_lo < roi_hi:
                ax.axvspan(roi_lo, roi_hi, alpha=0.15, color="green",
                           label="Peak {}-{}".format(roi_lo, roi_hi))
            norm_lo = self.norm_lo_ctrl.GetValue()
            norm_hi = self.norm_hi_ctrl.GetValue()
            if norm_lo < norm_hi:
                ax.axvspan(norm_lo, norm_hi, alpha=0.12, color="red",
                           label="Norm {}-{}".format(norm_lo, norm_hi))
            ax.legend(fontsize=7, loc="upper right")

        if xmin is not None or xmax is not None or ymin is not None:
            limits = [xmin, xmax, ymin, None]
            self.panel1.set_xylims(limits)
        if ylog:
            self.panel1.set_logscale(yscale='log')

        self.panel1.draw()
        self._plot1_checked = checked
        self._plot1_initialized = True


class MainFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="FLAME - Fluorescence XAFS Multi-Element Processor", size=(1200, 700))
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "flame_icon.ico")
        if os.path.exists(icon_path):
            self.SetIcon(wx.Icon(icon_path))
        self.panel = XrfViewerPanel(self)
        self.Show()


def main():
    app = wx.App(False)
    MainFrame()
    app.MainLoop()


if __name__ == "__main__":
    main()

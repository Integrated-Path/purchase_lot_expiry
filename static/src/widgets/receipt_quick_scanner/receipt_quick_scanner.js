/** @odoo-module **/

import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { _t } from "@web/core/l10n/translation";

// Arabic keyboard map on client side for instantaneous preprocessing
const AR_TO_EN_MAP = {
    'ذ': '`', 'ض': 'q', 'ص': 'w', 'ث': 'e', 'ق': 'r', 'ف': 't', 'غ': 'y', 'ع': 'u',
    'ه': 'i', 'خ': 'o', 'ح': 'p', 'ج': '[', 'د': ']', 'ش': 'a', 'س': 's', 'ي': 'd',
    'ب': 'f', 'ل': 'g', 'ا': 'h', 'ت': 'j', 'ن': 'k', 'م': 'l', 'ك': ';', 'ط': "'",
    'ئ': 'z', 'ء': 'x', 'ؤ': 'c', 'ر': 'v', 'لا': 'b', 'ى': 'n', 'ة': 'm', 'و': ',',
    'ز': '.', 'ظ': '/', 'َ': 'Q', 'ً': 'W', 'ُ': 'E', 'ٌ': 'R', 'لإ': 'T', 'إ': 'Y',
    '‘': 'U', '÷': 'I', '×': 'O', '؛': 'P', '<': '{', '>': '}', 'ِ': 'A', 'ٍ': 'S',
    ']': 'D', '[': 'F', 'لأ': 'G', 'أ': 'H', 'ـ': 'J', '،': 'K', '/': 'L', ':': ':',
    '"': '"', 'ْ': 'X', '}': 'C', '{': 'V', 'لآ': 'B', 'آ': 'N', "'": 'M', ',': '<',
    '.': '>', '؟': '?', '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4', '٥': '5',
    '٦': '6', '٧': '7', '٨': '8', '٩': '9', '۰': '0', '۱': '1', '۲': '2', '۳': '3',
    '۴': '4', '۵': '5', '۶': '6', '۷': '7', '۸': '8', '٩': '9',
};

function normalizeArabicText(str) {
    if (!str) return str;
    let res = "";
    let i = 0;
    while (i < str.length) {
        if (i + 1 < str.length && AR_TO_EN_MAP[str.slice(i, i + 2)]) {
            res += AR_TO_EN_MAP[str.slice(i, i + 2)];
            i += 2;
        } else if (AR_TO_EN_MAP[str[i]]) {
            res += AR_TO_EN_MAP[str[i]];
            i++;
        } else {
            res += str[i];
            i++;
        }
    }
    return res;
}

export class ReceiptQuickScanner extends Component {
    static template = "purchase_lot_expiry.ReceiptQuickScanner";
    static props = {
        ...standardWidgetProps,
    };

    setup() {
        this.inputRef = useRef("scannerInput");
        this.orm = useService("orm");
        this.debounceTimer = null;
        this.refocusInterval = null;

        this.state = useState({
            isProcessing: false,
            lastStatusMsg: _t("Ready for receipt scanning. Point scanner gun at product/lot QR code."),
            lastStatusType: "info",
            scanCount: 0,
        });

        onMounted(() => {
            this.focusInput();
            this.refocusInterval = setInterval(() => {
                if (document.activeElement !== this.inputRef.el && !this.state.isProcessing) {
                    this.focusInput();
                }
            }, 1500);
        });

        onWillUnmount(() => {
            if (this.debounceTimer) clearTimeout(this.debounceTimer);
            if (this.refocusInterval) clearInterval(this.refocusInterval);
        });
    }

    focusInput() {
        if (this.inputRef.el) {
            this.inputRef.el.focus();
        }
    }

    onKeyDown(ev) {
        if (ev.key === "Enter" || ev.keyCode === 13) {
            ev.preventDefault();
            ev.stopPropagation();
            if (this.debounceTimer) clearTimeout(this.debounceTimer);
            this.processScan();
        }
    }

    onInput() {
        if (this.debounceTimer) clearTimeout(this.debounceTimer);
        const val = this.inputRef.el ? this.inputRef.el.value.trim() : "";
        if (val.length >= 6) {
            this.debounceTimer = setTimeout(() => {
                this.processScan();
            }, 120);
        }
    }

    async processScan() {
        if (!this.inputRef.el) return;
        let rawVal = this.inputRef.el.value.trim();
        if (!rawVal || this.state.isProcessing) return;

        this.state.isProcessing = true;
        this.inputRef.el.value = "";

        const normalizedVal = normalizeArabicText(rawVal);
        const resModel = this.props.record.resModel;
        const resId = this.props.record.resId;

        try {
            const res = await this.orm.call(
                resModel,
                "action_quick_scan",
                [[resId], normalizedVal]
            );

            if (res && res.success) {
                this.playBeepSound(true);
                this.state.lastStatusMsg = res.message;
                this.state.lastStatusType = res.warning ? "warning" : "success";
                this.state.scanCount += 1;
            } else {
                this.playBeepSound(false);
                this.state.lastStatusMsg = res ? res.message : _t("Scan failed.");
                this.state.lastStatusType = "danger";
            }

            await this.props.record.load();

        } catch (err) {
            this.playBeepSound(false);
            this.state.lastStatusMsg = err.message || _t("Error processing scan.");
            this.state.lastStatusType = "danger";
        } finally {
            this.state.isProcessing = false;
            this.focusInput();
        }
    }

    playBeepSound(isSuccess) {
        try {
            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            if (!AudioCtx) return;
            const ctx = new AudioCtx();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);

            if (isSuccess) {
                osc.type = "sine";
                osc.frequency.setValueAtTime(880, ctx.currentTime);
                gain.gain.setValueAtTime(0.15, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.12);
                osc.start(ctx.currentTime);
                osc.stop(ctx.currentTime + 0.12);
                if (navigator.vibrate) navigator.vibrate(60);
            } else {
                osc.type = "sawtooth";
                osc.frequency.setValueAtTime(220, ctx.currentTime);
                gain.gain.setValueAtTime(0.20, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.25);
                osc.start(ctx.currentTime);
                osc.stop(ctx.currentTime + 0.25);
                if (navigator.vibrate) navigator.vibrate([100, 50, 100]);
            }
        } catch (e) {}
    }
}

registry.category("view_widgets").add("receipt_quick_scanner", {
    component: ReceiptQuickScanner,
});

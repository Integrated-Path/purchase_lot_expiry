/** @odoo-module **/

import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { loadJS } from "@web/core/assets";
import { _t } from "@web/core/l10n/translation";

export class MobileQrCameraScanner extends Component {
    static template = "purchase_lot_expiry.MobileQrCameraScanner";
    static props = {
        ...standardWidgetProps,
    };

    setup() {
        this.scannerContainerRef = useRef("scannerContainer");
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.scannerId = `mobile_qr_reader_${Date.now()}`;
        this.html5QrCode = null;
        this.lastScanCode = "";
        this.lastScanTime = 0;

        this.state = useState({
            isReady: false,
            isProcessing: false,
            statusMsg: _t("Initializing camera..."),
            statusType: "info",
            scanCount: 0,
        });

        onMounted(async () => {
            await this.initScanner();
        });

        onWillUnmount(async () => {
            await this.stopScanner();
        });
    }

    async initScanner() {
        try {
            if (!window.Html5Qrcode) {
                try {
                    await loadJS("/purchase_lot_expiry/static/src/lib/html5-qrcode.min.js");
                } catch (e) {
                    await loadJS("https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js");
                }
            }

            if (!this.scannerContainerRef.el) {
                return;
            }

            this.html5QrCode = new window.Html5Qrcode(this.scannerId);

            const qrConfig = {
                fps: 12,
                qrbox: (width, height) => {
                    const minEdge = Math.min(width, height);
                    const size = Math.floor(minEdge * 0.72);
                    return { width: size, height: size };
                },
                aspectRatio: 1.0,
            };

            await this.html5QrCode.start(
                { facingMode: "environment" },
                qrConfig,
                (decodedText) => this.onCodeScanned(decodedText),
                () => {}
            );

            this.state.isReady = true;
            this.state.statusMsg = _t("Camera active. Point at box label QR code.");
            this.state.statusType = "info";

        } catch (err) {
            this.state.isReady = false;
            this.state.statusType = "danger";
            this.state.statusMsg = _t("Camera access denied or unavailable: ") + (err.message || err);
        }
    }

    async stopScanner() {
        if (this.html5QrCode && this.html5QrCode.isScanning) {
            try {
                await this.html5QrCode.stop();
                await this.html5QrCode.clear();
            } catch (err) {}
            this.html5QrCode = null;
        }
    }

    async onCodeScanned(decodedText) {
        const now = Date.now();
        if (this.state.isProcessing) return;
        if (decodedText === this.lastScanCode && now - this.lastScanTime < 2500) {
            return;
        }

        this.state.isProcessing = true;
        this.lastScanCode = decodedText;
        this.lastScanTime = now;

        this.playBeepSound();
        if (navigator.vibrate) {
            navigator.vibrate(80);
        }

        try {
            const resId = this.props.record.resId;
            const res = await this.orm.call(
                "stock.picking.mobile.qr.wizard",
                "process_mobile_qr_scan",
                [[resId], decodedText]
            );

            if (res && res.success) {
                this.state.statusMsg = res.message;
                this.state.statusType = "success";
                this.state.scanCount += 1;
            } else {
                this.state.statusMsg = res ? res.message : _t("Scan failed.");
                this.state.statusType = "danger";
                if (navigator.vibrate) {
                    navigator.vibrate([100, 50, 100]);
                }
            }

            await this.props.record.load();

        } catch (err) {
            this.state.statusMsg = err.message || _t("Error contacting server.");
            this.state.statusType = "danger";
        } finally {
            setTimeout(() => {
                this.state.isProcessing = false;
            }, 600);
        }
    }

    playBeepSound() {
        try {
            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            if (!AudioCtx) return;
            const ctx = new AudioCtx();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.type = "sine";
            osc.frequency.setValueAtTime(880, ctx.currentTime);
            gain.gain.setValueAtTime(0.12, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.12);
            osc.start(ctx.currentTime);
            osc.stop(ctx.currentTime + 0.12);
        } catch (e) {}
    }
}

registry.category("view_widgets").add("mobile_qr_camera_scanner", {
    component: MobileQrCameraScanner,
});

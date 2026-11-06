"""Shared loader: imports ../vial_overlay.pyw so the tools reuse its HID code."""
import importlib.machinery, importlib.util, os, sys
sys.stdout.reconfigure(encoding="utf-8")
_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vial_overlay.pyw")
_loader = importlib.machinery.SourceFileLoader("vial_overlay", _path)
ov = importlib.util.module_from_spec(importlib.util.spec_from_loader("vial_overlay", _loader))
_loader.exec_module(ov)

def device():
    """-> raw HID device of the first Vial keyboard (no keymap read)"""
    found = ov.open_vial()
    if not found: sys.exit("No Vial keyboard found")
    return found[0]

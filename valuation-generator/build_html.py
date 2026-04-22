"""
Builds the full Radiant Intelligence™ HTML report from parsed data + insights.
Converts to PDF using Playwright/Chromium.
"""

import base64
import io
import math
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

from PIL import Image

# ── Logo processing ───────────────────────────────────────────────────────────
_LOGO_PATH = Path(__file__).parent / 'RR Logo.png'
_LOGO_B64 = None  # reset each process start


def _get_logo_b64() -> str:
    global _LOGO_B64
    if _LOGO_B64:
        return _LOGO_B64
    try:
        img = Image.open(_LOGO_PATH).convert('RGBA')
        arr_data = img.tobytes()
        w, h = img.size
        import struct
        # Convert ALL opaque pixels to white — full white logo on dark background
        pixels = list(img.getdata())
        new_pixels = []
        for r, g, b, a in pixels:
            if a > 10:
                new_pixels.append((255, 255, 255, a))
            else:
                new_pixels.append((0, 0, 0, 0))
        out = Image.new('RGBA', img.size)
        out.putdata(new_pixels)
        buf = io.BytesIO()
        out.save(buf, format='PNG')
        _LOGO_B64 = base64.b64encode(buf.getvalue()).decode()
        return _LOGO_B64
    except Exception:
        return ''


# ── Formatting helpers ────────────────────────────────────────────────────────
def _fmt_aed_short(val):
    if val is None:
        return 'N/A'
    if val >= 1_000_000:
        return f'AED {val/1_000_000:.2f}M'
    if val >= 1_000:
        return f'AED {val:,}'
    return f'AED {val}'


def _fmt_aed(val):
    if val is None:
        return 'N/A'
    return f'AED {val:,}'


def _fmt_num(val):
    if val is None:
        return 'N/A'
    return f'{val:,}'


# ── SVG price trend chart ─────────────────────────────────────────────────────
def _make_trend_svg(current_val, change_pct, range_low=None, range_high=None):
    """Generate a simple 6-point price trend SVG."""
    if not current_val:
        return ''

    # Back-calculate approximate historical values
    six_ago = current_val / (1 + change_pct / 100)
    # Simulate a gentle curve with 6 data points
    points_raw = [
        six_ago * 0.97,
        six_ago * 0.985,
        six_ago,
        six_ago * (1 + change_pct / 200),
        six_ago * (1 + change_pct / 150),
        current_val,
    ]

    # Normalize to SVG coords
    w, h = 520, 100
    pad_x, pad_y = 20, 10
    min_v = min(points_raw) * 0.98
    max_v = max(points_raw) * 1.02
    v_range = max_v - min_v or 1

    def to_x(i):
        return pad_x + (i / (len(points_raw) - 1)) * (w - 2 * pad_x)

    def to_y(v):
        return h - pad_y - ((v - min_v) / v_range) * (h - 2 * pad_y)

    coords = [(to_x(i), to_y(v)) for i, v in enumerate(points_raw)]
    path_d = 'M ' + ' L '.join(f'{x:.1f},{y:.1f}' for x, y in coords)

    # Area fill path (close to bottom)
    area_d = path_d + f' L {coords[-1][0]:.1f},{h} L {coords[0][0]:.1f},{h} Z'

    # Y-axis labels
    mid_v = (min_v + max_v) / 2

    def fmt_label(v):
        if v >= 1_000_000:
            return f'{v/1_000_000:.2f}M'
        return f'{v/1_000:.0f}K'

    # Month labels
    now = datetime.now()
    months = []
    for i in range(6, -1, -2):
        m = (now.month - i - 1) % 12 + 1
        months.append(datetime(now.year if m <= now.month else now.year - 1, m, 1).strftime('%b'))
    if len(months) < 4:
        months = ['Oct', 'Dec', 'Feb', 'Apr']

    lx = [to_x(i) for i in [0, 2, 4, 5]]

    svg = f'''<svg viewBox="0 0 {w} {h+30}" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto;">
  <defs>
    <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#B8975A" stop-opacity="0.25"/>
      <stop offset="100%" stop-color="#B8975A" stop-opacity="0"/>
    </linearGradient>
  </defs>
  <!-- Grid lines -->
  <line x1="{pad_x}" y1="{to_y(max_v):.1f}" x2="{w-pad_x}" y2="{to_y(max_v):.1f}" stroke="#1e2d47" stroke-width="1"/>
  <line x1="{pad_x}" y1="{to_y(mid_v):.1f}" x2="{w-pad_x}" y2="{to_y(mid_v):.1f}" stroke="#1e2d47" stroke-width="1"/>
  <line x1="{pad_x}" y1="{to_y(min_v):.1f}" x2="{w-pad_x}" y2="{to_y(min_v):.1f}" stroke="#1e2d47" stroke-width="1"/>
  <!-- Area fill -->
  <path d="{area_d}" fill="url(#trendFill)"/>
  <!-- Trend line -->
  <path d="{path_d}" fill="none" stroke="#B8975A" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
  <!-- Current value dot -->
  <circle cx="{coords[-1][0]:.1f}" cy="{coords[-1][1]:.1f}" r="4" fill="#B8975A"/>
  <!-- Y labels -->
  <text x="15" y="{to_y(max_v)+4:.1f}" fill="#6b7a99" font-size="9" font-family="DM Mono, monospace" text-anchor="end">{fmt_label(max_v)}</text>
  <text x="15" y="{to_y(mid_v)+4:.1f}" fill="#6b7a99" font-size="9" font-family="DM Mono, monospace" text-anchor="end">{fmt_label(mid_v)}</text>
  <text x="15" y="{to_y(min_v)+4:.1f}" fill="#6b7a99" font-size="9" font-family="DM Mono, monospace" text-anchor="end">{fmt_label(min_v)}</text>
  <!-- X labels -->
  <text x="{lx[0]:.1f}" y="{h+20}" fill="#6b7a99" font-size="9" font-family="DM Sans, sans-serif" text-anchor="middle">{months[0] if len(months)>0 else ''}</text>
  <text x="{lx[1]:.1f}" y="{h+20}" fill="#6b7a99" font-size="9" font-family="DM Sans, sans-serif" text-anchor="middle">{months[1] if len(months)>1 else ''}</text>
  <text x="{lx[2]:.1f}" y="{h+20}" fill="#6b7a99" font-size="9" font-family="DM Sans, sans-serif" text-anchor="middle">{months[2] if len(months)>2 else ''}</text>
  <text x="{lx[3]:.1f}" y="{h+20}" fill="#6b7a99" font-size="9" font-family="DM Sans, sans-serif" text-anchor="middle">{months[3] if len(months)>3 else ''}</text>
</svg>'''
    return svg


# ── HTML assembly ─────────────────────────────────────────────────────────────
def build_html(data: dict, agent_name: str, insights: list) -> str:
    logo_b64 = _get_logo_b64()
    logo_src = f'data:image/png;base64,{logo_b64}' if logo_b64 else ''

    val = data.get('value')
    psf = data.get('price_per_sqft')
    change_str = data.get('six_month_change_str', '+0.00%')
    change = data.get('six_month_change', 0.0)
    confidence = data.get('confidence', 'High Confidence')
    beds = data.get('bedrooms', 0)
    sqft = data.get('area_sqft', 0)
    unit = data.get('unit_number', '')
    building = data.get('building', '')
    area = data.get('area', '')
    community = data.get('community', '')
    city = data.get('city', 'Dubai')
    view = data.get('view', '')
    furnishing = data.get('furnishing', '')
    prop_type = data.get('property_type', 'Apartment')
    range_low = data.get('range_low')
    range_high = data.get('range_high')
    sales = data.get('comparable_sales', [])
    listings = data.get('active_listings', [])
    gross_yield = data.get('gross_yield')

    # Acquisition cost
    total_acq = data.get('total_acquisition')
    dld_fee = data.get('dld_fee')
    agency_fee = data.get('agency_fee')
    reg_fee = data.get('registration_fee', 4200)
    mortgage_reg = data.get('mortgage_reg_fee', 2980)
    mortgage_val_fee = data.get('mortgage_val_fee', 3150)
    bank_fee = data.get('bank_arrangement_fee')

    beds_label = 'Studio' if beds == 0 else f'{beds} Bedroom{"s" if beds != 1 else ""}'
    location_line = f'{building}, {area}, {city}'
    unit_line = f'UNIT {unit} · {beds_label.upper()} · {sqft:,} SQFT' if unit and sqft else (
        f'{beds_label.upper()} · {sqft:,} SQFT' if sqft else beds_label.upper()
    )

    today = datetime.now().strftime('%-d %B %Y')
    change_positive = change >= 0

    # Range display
    def fmt_range(v):
        if v is None:
            return 'N/A'
        if v >= 1_000_000:
            return f'AED {v/1_000_000:.2f}M'
        return f'AED {v:,}'

    range_display = f'{fmt_range(range_low)} – {fmt_range(range_high)}' if range_low and range_high else 'N/A'

    # Yield / 3rd stat
    if gross_yield:
        stat3_value = f'{gross_yield}%'
        stat3_label = 'GROSS RENTAL YIELD'
        stat3_sub = 'Annual income'
    else:
        stat3_value = f'AED {psf:,}' if psf else 'N/A'
        stat3_label = 'PRICE PER SQFT'
        stat3_sub = 'Market rate'

    trend_svg = _make_trend_svg(val, change, range_low, range_high)

    # ── Sales table rows ──────────────────────────────────────────────────────
    def sales_rows():
        if not sales:
            return '<tr><td colspan="5" style="text-align:center;color:#6b7a99;padding:16px">No comparable sales data available</td></tr>'
        rows = []
        for s in sales:
            psf_s = round(s['price'] / s['area_sqft']) if s.get('area_sqft') and s['area_sqft'] > 0 else None
            rows.append(f'''
            <tr>
              <td>{s.get("date","")}</td>
              <td>{s.get("address","")}</td>
              <td style="text-align:center">{s.get("beds","")}</td>
              <td style="text-align:right">{s.get("area_sqft",""):,}</td>
              <td style="text-align:right">{_fmt_aed(s.get("price"))}</td>
              <td style="text-align:right;color:#B8975A">{_fmt_aed(psf_s)}</td>
            </tr>''')
        return '\n'.join(rows)

    # ── Listings table rows ───────────────────────────────────────────────────
    def listing_rows():
        if not listings:
            return '<tr><td colspan="5" style="text-align:center;color:#6b7a99;padding:16px">No active listing data available</td></tr>'
        rows = []
        for l in listings[:8]:
            rows.append(f'''
            <tr>
              <td>{l.get("property","")}</td>
              <td style="text-align:center">{l.get("beds","")}</td>
              <td style="text-align:right">{l.get("area_sqft",""):,}</td>
              <td style="text-align:right">{_fmt_aed(l.get("price"))}</td>
            </tr>''')
        return '\n'.join(rows)

    # ── Insight blocks ────────────────────────────────────────────────────────
    def insight_blocks():
        blocks = []
        for ins in insights:
            blocks.append(f'''
            <div class="insight-item">
              <div class="insight-num">{ins["number"]}</div>
              <div class="insight-content">
                <div class="insight-title">{ins["title"]}</div>
                <div class="insight-body">{ins["body"]}</div>
              </div>
            </div>''')
        return '\n'.join(blocks)

    # ── Cost rows ─────────────────────────────────────────────────────────────
    def cost_rows():
        rows = [
            ('Property Value', val),
            (f'DLD Fee (4%)', dld_fee),
            ('Registration Trustee Fee', reg_fee),
            (f'Agency Fee (2% + VAT)', agency_fee),
            ('Mortgage Registration', mortgage_reg),
            ('Mortgage Valuation', mortgage_val_fee),
            (f'Bank Arrangement Fee (~0.5%)', bank_fee),
        ]
        html_rows = []
        for label, amount in rows:
            if amount is None:
                continue
            html_rows.append(f'<div class="cost-row"><span>{label}</span><span class="cost-amt">{_fmt_aed(amount)}</span></div>')
        return '\n'.join(html_rows)

    # ── Logo HTML ─────────────────────────────────────────────────────────────
    logo_html = f'<img src="{logo_src}" class="logo-img" alt="Radiant Realtors"/>' if logo_src else '<div class="logo-text">RADIANT REALTORS</div>'

    # ── Property details cards ────────────────────────────────────────────────
    details = [
        ('DEVELOPMENT', building or 'N/A'),
        ('COMMUNITY', f'{area}, {city}' if area else city),
        ('BEDROOMS', beds_label),
        ('BUILT-UP AREA', f'{sqft:,} sqft' if sqft else 'N/A'),
        ('UNIT NUMBER', unit or 'N/A'),
        ('VIEW', view or 'N/A'),
    ]
    detail_cards = '\n'.join(
        f'<div class="detail-card"><div class="detail-label">{k}</div><div class="detail-value">{v}</div></div>'
        for k, v in details
    )

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Radiant Intelligence™ — {building} {unit}</title>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;0,500;0,600;1,300;1,400&family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@300;400;500&display=swap" rel="stylesheet"/>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  :root {{
    --navy: #0C1220;
    --navy2: #111827;
    --gold: #B8975A;
    --gold-light: #d4b87a;
    --text: #e8e4dc;
    --text-dim: #8a96aa;
    --border: #1e2d47;
    --card-bg: #131c2e;
  }}

  html, body {{
    background: #0C1220;
    margin: 0;
    padding: 0;
    font-family: 'DM Sans', sans-serif;
    color: var(--text);
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }}

  @media print {{
    html, body {{
      background: #0C1220 !important;
      margin: 0 !important;
      padding: 0 !important;
    }}
    @page {{ margin: 0; size: A4; }}
  }}

  .page {{
    width: 210mm;
    height: 297mm;
    min-height: 297mm;
    max-height: 297mm;
    overflow: hidden;
    background: #0C1220 !important;
    position: relative;
    page-break-after: always;
    break-after: page;
    display: flex;
    flex-direction: column;
    margin: 0;
    padding: 0;
    box-sizing: border-box;
  }}
  .page::before {{
    content: '';
    position: absolute;
    inset: 0;
    background: #0C1220;
    z-index: -1;
  }}
  .page:last-child {{
    page-break-after: avoid;
    break-after: avoid;
  }}

  /* ── Shared header / footer ── */
  .page-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10mm 12mm 6mm;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }}
  .logo-img {{ height: 28px; width: auto; }}
  .logo-text {{ font-family: 'Cormorant Garamond', serif; font-size: 14px; color: var(--gold); letter-spacing: 2px; }}
  .page-label {{ font-family: 'DM Mono', monospace; font-size: 9px; color: var(--text-dim); letter-spacing: 1px; }}
  .page-indicator {{ font-family: 'DM Mono', monospace; font-size: 10px; color: var(--gold); letter-spacing: 1px; }}

  .page-footer {{
    margin-top: auto;
    padding: 4mm 12mm;
    border-top: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-shrink: 0;
  }}
  .footer-text {{ font-size: 8px; color: var(--text-dim); font-family: 'DM Mono', monospace; letter-spacing: 0.5px; }}

  /* ── Cover page ── */
  .cover {{ background: var(--navy); }}
  .cover-body {{
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 0 14mm;
  }}
  .cover-badge {{
    display: inline-block;
    border: 1px solid var(--gold);
    color: var(--gold);
    font-family: 'DM Mono', monospace;
    font-size: 8px;
    letter-spacing: 2px;
    padding: 4px 10px;
    margin-bottom: 6mm;
    width: fit-content;
  }}
  .cover-subtitle {{
    font-family: 'DM Mono', monospace;
    font-size: 9px;
    color: var(--text-dim);
    letter-spacing: 3px;
    margin-bottom: 3mm;
  }}
  .cover-title {{
    font-family: 'Cormorant Garamond', serif;
    font-size: 36px;
    font-weight: 300;
    color: var(--text);
    line-height: 1.15;
    margin-bottom: 4mm;
  }}
  .cover-address {{
    font-size: 13px;
    color: var(--text-dim);
    margin-bottom: 2mm;
  }}
  .cover-unit-line {{
    font-family: 'DM Mono', monospace;
    font-size: 10px;
    color: var(--gold);
    letter-spacing: 2px;
    margin-bottom: 8mm;
  }}
  .cover-divider {{
    width: 48px;
    height: 1px;
    background: var(--gold);
    margin-bottom: 8mm;
  }}
  .cover-stats {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 4mm;
    margin-bottom: 8mm;
  }}
  .cover-stat {{
    border-left: 2px solid var(--gold);
    padding-left: 4mm;
  }}
  .cover-stat-value {{
    font-family: 'DM Mono', monospace;
    font-size: 18px;
    color: var(--text);
    font-weight: 500;
  }}
  .cover-stat-label {{
    font-family: 'DM Mono', monospace;
    font-size: 8px;
    color: var(--gold);
    letter-spacing: 1.5px;
    margin-top: 2px;
  }}
  .cover-stat-sub {{
    font-size: 9px;
    color: var(--text-dim);
    margin-top: 2px;
  }}
  .ai-badge-row {{
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 6mm;
  }}
  .ai-badge {{
    background: rgba(184,151,90,0.12);
    border: 1px solid rgba(184,151,90,0.4);
    padding: 5px 10px;
    font-size: 9px;
    font-family: 'DM Mono', monospace;
    color: var(--gold);
    letter-spacing: 1px;
  }}
  .ai-badge-desc {{
    font-size: 9px;
    color: var(--text-dim);
    line-height: 1.4;
    max-width: 340px;
  }}

  /* Prepared-by banner */
  .prepared-banner {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    display: grid;
    grid-template-columns: 1fr 1fr;
    padding: 4mm 5mm;
    gap: 2mm;
    margin-bottom: 4mm;
  }}
  .banner-section {{ display: flex; flex-direction: column; gap: 2px; }}
  .banner-label {{ font-family: 'DM Mono', monospace; font-size: 7px; color: var(--text-dim); letter-spacing: 1.5px; }}
  .banner-agent {{ font-family: 'Cormorant Garamond', serif; font-size: 16px; color: var(--text); font-weight: 500; }}
  .banner-company {{ font-size: 9px; color: var(--text-dim); }}
  .banner-ref {{ font-family: 'DM Mono', monospace; font-size: 9px; color: var(--text-dim); line-height: 1.6; }}
  .banner-ref span {{ color: var(--gold); }}

  /* ── Content pages ── */
  .page-content {{
    flex: 1;
    overflow: hidden;
    padding: 6mm 12mm;
    display: flex;
    flex-direction: column;
    gap: 5mm;
  }}

  .section-header {{
    font-family: 'DM Mono', monospace;
    font-size: 8px;
    letter-spacing: 2.5px;
    color: var(--text-dim);
    border-bottom: 1px solid var(--border);
    padding-bottom: 3mm;
    margin-bottom: 1mm;
  }}
  .section-header span {{ color: var(--gold); }}

  /* Valuation hero */
  .valuation-hero {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    padding: 5mm 6mm;
    display: flex;
    flex-direction: column;
    gap: 3mm;
  }}
  .val-label {{ font-family: 'DM Mono', monospace; font-size: 8px; color: var(--text-dim); letter-spacing: 2px; }}
  .val-amount {{
    font-family: 'Cormorant Garamond', serif;
    font-size: 40px;
    font-weight: 300;
    color: var(--text);
    line-height: 1;
  }}
  .val-meta {{ display: flex; gap: 6mm; align-items: center; flex-wrap: wrap; }}
  .val-badge {{
    background: rgba(184,151,90,0.15);
    border: 1px solid rgba(184,151,90,0.5);
    font-family: 'DM Mono', monospace;
    font-size: 8px;
    color: var(--gold);
    padding: 3px 8px;
    letter-spacing: 1px;
  }}
  .val-meta-item {{ font-family: 'DM Mono', monospace; font-size: 10px; color: var(--text-dim); }}
  .val-meta-item span {{ color: var(--text); }}
  .val-change {{ font-family: 'DM Mono', monospace; font-size: 12px; }}
  .positive {{ color: #4ade80; }}
  .negative {{ color: #f87171; }}

  .chart-container {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    padding: 4mm 4mm 2mm;
  }}
  .chart-label {{ font-family: 'DM Mono', monospace; font-size: 7px; color: var(--text-dim); letter-spacing: 1.5px; margin-bottom: 2mm; }}

  /* Detail cards */
  .detail-grid {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 2mm;
  }}
  .detail-card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    padding: 3mm 4mm;
  }}
  .detail-label {{ font-family: 'DM Mono', monospace; font-size: 7px; color: var(--text-dim); letter-spacing: 1.5px; margin-bottom: 2px; }}
  .detail-value {{ font-size: 11px; color: var(--text); font-weight: 500; }}

  /* Insights */
  .insight-item {{
    display: flex;
    gap: 4mm;
    padding: 3mm 0;
    border-bottom: 1px solid var(--border);
  }}
  .insight-item:last-child {{ border-bottom: none; }}
  .insight-num {{
    font-family: 'DM Mono', monospace;
    font-size: 11px;
    color: var(--gold);
    flex-shrink: 0;
    width: 16px;
    padding-top: 1px;
  }}
  .insight-content {{ flex: 1; }}
  .insight-title {{ font-size: 10px; font-weight: 600; color: var(--text); margin-bottom: 2px; }}
  .insight-body {{ font-size: 9px; color: var(--text-dim); line-height: 1.5; }}

  /* Cost breakdown */
  .cost-breakdown {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    padding: 4mm 5mm;
  }}
  .cost-total-row {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--gold);
    padding-bottom: 3mm;
    margin-bottom: 3mm;
  }}
  .cost-total-label {{ font-family: 'Cormorant Garamond', serif; font-size: 14px; color: var(--text); }}
  .cost-total-value {{ font-family: 'DM Mono', monospace; font-size: 14px; color: var(--gold); font-weight: 500; }}
  .cost-total-sub {{ font-size: 8px; color: var(--text-dim); margin-top: 2px; }}
  .cost-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5mm 4mm; }}
  .cost-row {{ display: flex; justify-content: space-between; align-items: center; padding: 1.5mm 0; border-bottom: 1px solid var(--border); }}
  .cost-row:last-child {{ border-bottom: none; }}
  .cost-row span {{ font-size: 9px; color: var(--text-dim); }}
  .cost-amt {{ font-family: 'DM Mono', monospace; font-size: 9px; color: var(--text) !important; }}

  /* Tables */
  .data-table {{ width: 100%; border-collapse: collapse; font-size: 9px; }}
  .data-table thead tr {{ background: rgba(184,151,90,0.1); }}
  .data-table th {{ font-family: 'DM Mono', monospace; font-size: 7.5px; letter-spacing: 1px; color: var(--gold); padding: 3mm 3mm; text-align: left; border-bottom: 1px solid var(--border); font-weight: 500; }}
  .data-table td {{ padding: 2.5mm 3mm; color: var(--text-dim); border-bottom: 1px solid var(--border); }}
  .data-table tbody tr:last-child td {{ border-bottom: none; }}
  .data-table tbody tr:hover td {{ color: var(--text); }}

  .table-section {{ display: flex; flex-direction: column; gap: 2mm; flex: 1; }}
  .table-title {{ font-family: 'DM Mono', monospace; font-size: 8px; color: var(--text); letter-spacing: 1.5px; }}
  .table-subtitle {{ font-size: 8px; color: var(--text-dim); }}
  .table-wrapper {{ background: var(--card-bg); border: 1px solid var(--border); overflow: hidden; }}

  /* Disclaimer */
  .disclaimer {{
    font-size: 7.5px;
    color: var(--text-dim);
    line-height: 1.5;
    border-top: 1px solid var(--border);
    padding-top: 3mm;
    margin-top: auto;
  }}
</style>
</head>
<body>

<!-- ════════════════════════════════════════════════════════ COVER ══ -->
<div class="page cover">
  <div class="page-header">
    {logo_html}
    <div style="text-align:right">
      <div style="font-family:'DM Mono',monospace;font-size:8px;color:var(--gold);letter-spacing:2px">RADIANT INTELLIGENCE™</div>
      <div style="font-family:'DM Mono',monospace;font-size:7px;color:var(--text-dim);letter-spacing:1.5px">AI-DRIVEN MARKET ANALYTICS</div>
    </div>
  </div>

  <div class="cover-body">
    <div class="cover-badge">⚡ RADIANT INTELLIGENCE™</div>
    <div class="cover-subtitle">AI-DRIVEN MARKET ANALYTICS</div>
    <div class="cover-title">Property Valuation<br/>Report</div>
    <div class="cover-address">{location_line}</div>
    <div class="cover-unit-line">{unit_line}</div>
    <div class="cover-divider"></div>

    <div class="cover-stats">
      <div class="cover-stat">
        <div class="cover-stat-value">{_fmt_aed_short(val)}</div>
        <div class="cover-stat-label">ESTIMATED VALUE</div>
        <div class="cover-stat-sub">{confidence}</div>
      </div>
      <div class="cover-stat">
        <div class="cover-stat-value {'positive' if change_positive else 'negative'}">{change_str}</div>
        <div class="cover-stat-label">6-MONTH GROWTH</div>
        <div class="cover-stat-sub">Price appreciation</div>
      </div>
      <div class="cover-stat">
        <div class="cover-stat-value">{stat3_value}</div>
        <div class="cover-stat-label">{stat3_label}</div>
        <div class="cover-stat-sub">{stat3_sub}</div>
      </div>
    </div>

    <div class="ai-badge-row">
      <div class="ai-badge">⚡ Powered by Radiant Intelligence™</div>
    </div>
    <div class="ai-badge-desc" style="font-size:8.5px;color:var(--text-dim);margin-bottom:6mm;line-height:1.5">
      This report is generated using our proprietary analytics engine trained on DLD transaction data,
      live listings, and sub-community micro-trends across Dubai.
    </div>

    <div class="prepared-banner">
      <div class="banner-section">
        <div class="banner-label">PREPARED BY</div>
        <div class="banner-agent">{agent_name}</div>
        <div class="banner-company">Radiant Realtors · radiantrealtors.ae</div>
      </div>
      <div class="banner-section" style="border-left:1px solid var(--border);padding-left:4mm">
        <div class="banner-label">REPORT REFERENCE</div>
        <div class="banner-ref">
          {'<span>' + unit + ' · </span>' if unit else ''}<span>{building}</span><br/>
          Generated: {today} · <span>Radiant Intelligence™ v2.1</span>
        </div>
      </div>
    </div>
  </div>

  <div class="page-footer">
    <div class="footer-text">RADIANT INTELLIGENCE™ · CONFIDENTIAL · FOR CLIENT USE ONLY</div>
    <div class="footer-text">RADIANTREALTORS.AE · Generated {today}</div>
  </div>
</div>


<!-- ════════════════════════════════════════════════════════ PAGE 1: VALUATION ══ -->
<div class="page">
  <div class="page-header">
    {logo_html}
    <div style="display:flex;align-items:center;gap:6mm">
      <div class="page-label">VALUATION ANALYSIS</div>
      <div class="page-indicator">01 / 03</div>
    </div>
  </div>

  <div class="page-content">
    <div class="section-header">MARKET VALUATION · <span>{building}, {area}</span></div>

    <div class="valuation-hero">
      <div class="val-label">RADIANT INTELLIGENCE™ ESTIMATE</div>
      <div class="val-amount">{_fmt_aed(val)}</div>
      <div class="val-meta">
        <div class="val-badge">{confidence}</div>
        <div class="val-meta-item">AED <span>{psf:,}/sqft</span></div>
        <div class="val-meta-item">Range <span>{range_display}</span></div>
        <div class="val-change {'positive' if change_positive else 'negative'}">{'▲' if change_positive else '▼'} {change_str} (6 months)</div>
      </div>
    </div>

    <div class="chart-container">
      <div class="chart-label">6-MONTH PRICE TREND · INDICATIVE</div>
      {trend_svg}
    </div>

    <div class="section-header">PROPERTY DETAILS</div>
    <div class="detail-grid">
      {detail_cards}
    </div>
  </div>

  <div class="page-footer">
    <div class="footer-text">Radiant Intelligence™ · Confidential · radiantrealtors.ae</div>
    <div class="footer-text">Prepared by {agent_name} · Generated {today}</div>
  </div>
</div>


<!-- ════════════════════════════════════════════════════════ PAGE 2: INSIGHTS ══ -->
<div class="page">
  <div class="page-header">
    {logo_html}
    <div style="display:flex;align-items:center;gap:6mm">
      <div class="page-label">AI INSIGHTS &amp; ACQUISITION COST</div>
      <div class="page-indicator">02 / 03</div>
    </div>
  </div>

  <div class="page-content">
    <div class="section-header">RADIANT INTELLIGENCE™ INSIGHTS · <span>Proprietary analysis · {today}</span></div>

    <div style="display:flex;flex-direction:column;flex:1;gap:0">
      {insight_blocks()}
    </div>

    <div class="section-header" style="margin-top:3mm">ACQUISITION COST BREAKDOWN</div>
    <div class="cost-breakdown">
      <div class="cost-total-row">
        <div>
          <div class="cost-total-label">Total Acquisition Cost</div>
          <div class="cost-total-sub">Value + all DLD and transaction fees</div>
        </div>
        <div class="cost-total-value">{_fmt_aed(total_acq)}</div>
      </div>
      <div class="cost-grid">
        {cost_rows()}
      </div>
    </div>
  </div>

  <div class="page-footer">
    <div class="footer-text">Radiant Intelligence™ · Confidential · radiantrealtors.ae</div>
    <div class="footer-text">Prepared by {agent_name} · Generated {today}</div>
  </div>
</div>


<!-- ════════════════════════════════════════════════════════ PAGE 3: COMPARABLES ══ -->
<div class="page">
  <div class="page-header">
    {logo_html}
    <div style="display:flex;align-items:center;gap:6mm">
      <div class="page-label">COMPARABLE TRANSACTIONS</div>
      <div class="page-indicator">03 / 03</div>
    </div>
  </div>

  <div class="page-content">
    <div class="table-section">
      <div class="section-header">RECENT SALES TRANSACTIONS · <span>{len(sales)} comparable sales recorded</span></div>
      <div class="table-wrapper">
        <table class="data-table">
          <thead>
            <tr>
              <th>DATE</th>
              <th>DEVELOPMENT</th>
              <th style="text-align:center">BEDS</th>
              <th style="text-align:right">AREA (SQFT)</th>
              <th style="text-align:right">SOLD AT</th>
              <th style="text-align:right">PRICE / SQFT</th>
            </tr>
          </thead>
          <tbody>
            {sales_rows()}
          </tbody>
        </table>
      </div>
    </div>

    <div class="table-section">
      <div class="section-header">ACTIVE LISTINGS FOR SALE · <span>{len(listings)} comparable units advertised</span></div>
      <div class="table-wrapper">
        <table class="data-table">
          <thead>
            <tr>
              <th>PROPERTY</th>
              <th style="text-align:center">BEDS</th>
              <th style="text-align:right">AREA (SQFT)</th>
              <th style="text-align:right">LISTING PRICE</th>
            </tr>
          </thead>
          <tbody>
            {listing_rows()}
          </tbody>
        </table>
      </div>
    </div>

    <div class="prepared-banner" style="margin-top:auto">
      <div class="banner-section">
        <div class="banner-label">PREPARED BY</div>
        <div class="banner-agent">{agent_name}</div>
        <div class="banner-company">Radiant Realtors · radiantrealtors.ae</div>
      </div>
      <div class="banner-section" style="border-left:1px solid var(--border);padding-left:4mm">
        <div class="banner-label">REPORT REFERENCE</div>
        <div class="banner-ref">
          {'<span>' + unit + ' · </span>' if unit else ''}<span>{building}</span><br/>
          Generated: {today} · <span>Radiant Intelligence™ v2.1</span>
        </div>
      </div>
    </div>

    <div class="disclaimer">
      For informational purposes only. Not an official valuation or appraisal. Estimates derived from DLD transaction data
      for comparable properties assuming vacant possession. Values may vary based on finish, floor, and fit-out.
      Not to be relied upon for any transactional decision. Radiant Realtors LLC disclaims all liability.
      Figures indicative as of {today}.
    </div>
  </div>

  <div class="page-footer">
    <div class="footer-text">Radiant Intelligence™ · Confidential · Prepared by {agent_name} · radiantrealtors.ae</div>
    <div class="footer-text">Generated {today}</div>
  </div>
</div>

</body>
</html>'''
    return html


def render_pdf(html: str, output_path: str) -> str:
    """Render HTML to PDF using Playwright/Chromium."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(args=['--force-color-profile=srgb'])
        page = browser.new_page(viewport={'width': 794, 'height': 1123})
        page.set_content(html, wait_until='networkidle')
        # Force backgrounds on every element including page canvas
        page.add_style_tag(content='''
            @page { margin: 0; size: A4; background: #0C1220; }
            html, body { background: #0C1220 !important; margin: 0 !important; padding: 0 !important; }
            .page { background: #0C1220 !important; }
        ''')
        page.pdf(
            path=output_path,
            format='A4',
            print_background=True,
            margin={'top': '0', 'right': '0', 'bottom': '0', 'left': '0'},
        )
        browser.close()
    return output_path

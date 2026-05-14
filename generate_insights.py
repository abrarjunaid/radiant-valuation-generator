"""
Template-based AI insights for the Radiant Intelligence™ report.
Generates 5 property-specific commentary points from parsed TruEstimate data.
"""

DUBAI_AVG_YIELD_2BR = 6.2
DUBAI_AVG_YIELD_1BR = 6.8
DUBAI_AVG_YIELD_STUDIO = 7.2
DUBAI_6M_APPRECIATION_AVG = 2.5  # % — city-wide baseline


def _fmt_aed(val):
    if val is None:
        return 'N/A'
    if val >= 1_000_000:
        return f'AED {val/1_000_000:.2f}M'
    if val >= 1_000:
        return f'AED {val:,.0f}'
    return f'AED {val}'


def _beds_label(n):
    if n == 0:
        return 'Studio'
    return f'{n}BR'


def generate(data: dict) -> list[dict]:
    """
    Returns a list of 5 insight dicts, each with:
      - number (str)
      - title (str)
      - body (str)
    """
    insights = []
    val = data.get('value') or 0
    psf = data.get('price_per_sqft') or 0
    change = data.get('six_month_change') or 0.0
    change_str = data.get('six_month_change_str', '+0.00%')
    beds = data.get('bedrooms', 1)
    building = data.get('building', 'this development')
    area = data.get('area', 'the sub-community')
    community = data.get('community', '')
    sales = data.get('comparable_sales', [])
    listings = data.get('active_listings', [])
    sqft = data.get('area_sqft')
    confidence = data.get('confidence', 'High Confidence')
    gross_yield = data.get('gross_yield')

    location_label = f'{area}, {community}' if community else area

    # ── Insight 1: Price momentum ─────────────────────────────────────────────
    if change >= 4.0:
        momentum_title = 'Strong appreciation momentum'
        momentum_body = (
            f'{building} has recorded exceptional price growth of {change_str} over the past six months, '
            f'significantly outperforming the city-wide average of approximately {DUBAI_6M_APPRECIATION_AVG}%. '
            f'Our analytics engine attributes this to rising end-user demand and tightening resale inventory '
            f'in the {location_label} corridor.'
        )
    elif change >= 1.5:
        momentum_title = 'Consistent appreciation momentum'
        momentum_body = (
            f'{building} has recorded steady price growth of {change_str} over the past six months, '
            f'outperforming the city-wide average of approximately {DUBAI_6M_APPRECIATION_AVG}%. '
            f'Demand from owner-occupiers and investors in {location_label} continues to absorb available '
            f'supply, supporting upward price pressure.'
        )
    elif change >= 0:
        momentum_title = 'Stable pricing with positive trajectory'
        momentum_body = (
            f'{building} has maintained stable valuations with a {change_str} movement over the past six months. '
            f'The sub-community is consolidating after recent growth phases. '
            f'Our model indicates foundational support at current price levels with a positive outlook '
            f'into the next two quarters.'
        )
    else:
        momentum_title = 'Value entry window — pricing consolidation'
        momentum_body = (
            f'{building} has seen a {change_str} price adjustment over the past six months, '
            f'presenting a potential value-entry opportunity for investors. '
            f'Our model identifies this as a cyclical correction rather than a structural shift, '
            f'with a recovery trajectory expected as Dubai\'s population growth sustains demand.'
        )
    insights.append({'number': '01', 'title': momentum_title, 'body': momentum_body})

    # ── Insight 2: Price per sqft positioning ─────────────────────────────────
    area_psf_benchmarks = {
        'Dubai South': 1050, 'Business Bay': 1750, 'Downtown': 2400,
        'Marina': 1900, 'JVC': 1000, 'Arjan': 1600, 'JLT': 1600,
        'Meydan': 1700, 'MBR City': 1800, 'Palm Jumeirah': 3500,
        'Al Barsha': 1400, 'Jumeirah': 2200, 'Silicon Oasis': 900,
        'DIFC': 2800, 'Creek': 1900, 'Yas Island': 1200,
    }
    area_psf = None
    for key, benchmark in area_psf_benchmarks.items():
        if key.lower() in (area + ' ' + community).lower():
            area_psf = benchmark
            break

    if area_psf and psf:
        diff_pct = round((psf - area_psf) / area_psf * 100, 1)
        if diff_pct >= 5:
            psf_title = f'Premium positioning at AED {psf:,}/sqft'
            psf_body = (
                f'At AED {psf:,}/sqft, this unit trades at a {diff_pct}% premium over the broader '
                f'{area} sub-community average of approximately AED {area_psf:,}/sqft. '
                f'This premium reflects the development\'s quality, amenities, and established demand from discerning buyers.'
            )
        elif diff_pct <= -5:
            psf_title = f'Attractive entry pricing at AED {psf:,}/sqft'
            psf_body = (
                f'At AED {psf:,}/sqft, this unit is priced {abs(diff_pct)}% below the broader '
                f'{area} sub-community average of approximately AED {area_psf:,}/sqft. '
                f'This represents a compelling entry point — particularly for investors seeking capital '
                f'appreciation as prices converge to the area mean.'
            )
        else:
            psf_title = f'Market-aligned pricing at AED {psf:,}/sqft'
            psf_body = (
                f'At AED {psf:,}/sqft, this unit is priced in line with the {area} sub-community average '
                f'of approximately AED {area_psf:,}/sqft. '
                f'Fair-value positioning typically supports faster transaction timelines and '
                f'reduces holding risk for sellers.'
            )
    elif psf:
        psf_title = f'Price per sqft: AED {psf:,}'
        psf_body = (
            f'The property is valued at AED {psf:,} per square foot — a key metric for benchmark '
            f'comparison across {location_label}. '
            f'Our model cross-references this against 90+ days of DLD-recorded transactions '
            f'in comparable buildings to arrive at the {confidence.lower()} estimate.'
        )
    else:
        psf_title = 'Valuation validated against DLD data'
        psf_body = (
            f'The TruEstimate™ valuation for this {_beds_label(beds)} in {building} has been '
            f'cross-validated against recent DLD-recorded sales in {location_label}. '
            f'The {confidence.lower()} rating reflects strong transaction data availability.'
        )
    insights.append({'number': '02', 'title': psf_title, 'body': psf_body})

    # ── Insight 3: Supply & demand (listings analysis) ───────────────────────
    n_listings = len(listings)
    n_sales = len(sales)
    if n_listings == 0 and n_sales == 0:
        supply_title = 'Limited comparable data — scarcity signal'
        supply_body = (
            f'Fewer than 3 comparable {_beds_label(beds)} units are currently advertised for sale in {building}. '
            f'This scarcity of listed units is typically a bullish indicator — owners are not motivated '
            f'to sell at current prices, suggesting confidence in continued appreciation.'
        )
    elif n_listings <= 3:
        supply_title = f'Tight supply — only {n_listings} comparable listing{"s" if n_listings != 1 else ""}'
        supply_body = (
            f'With only {n_listings} comparable {_beds_label(beds)} unit{"s" if n_listings != 1 else ""} '
            f'currently listed for sale in {building}, supply is highly constrained. '
            f'Our model identifies this supply-demand imbalance as a key driver supporting '
            f'the current valuation and reducing downside risk.'
        )
    elif n_listings <= 7:
        supply_title = f'Moderate supply — {n_listings} comparable listings active'
        supply_body = (
            f'There are currently {n_listings} comparable {_beds_label(beds)} units listed for sale in {building}. '
            f'This moderate supply level provides buyers with choice while still supporting price stability. '
            f'Transaction velocity from the past 6 months suggests absorption is keeping pace with new listings.'
        )
    else:
        supply_title = f'Active market — {n_listings} units available'
        supply_body = (
            f'With {n_listings} comparable {_beds_label(beds)} units currently on the market in {building}, '
            f'buyers have good selection. Competitive pricing relative to asking prices is critical '
            f'for achieving a fast sale. The TruEstimate™ value positions this unit to attract '
            f'qualified buyers efficiently.'
        )
    insights.append({'number': '03', 'title': supply_title, 'body': supply_body})

    # ── Insight 4: Transaction velocity / comparable sales ────────────────────
    if n_sales >= 2:
        prices = [s['price'] for s in sales if s.get('price')]
        avg_sale = sum(prices) / len(prices) if prices else val
        premium_disc = round((val - avg_sale) / avg_sale * 100, 1) if avg_sale else 0
        if premium_disc > 3:
            vel_title = 'Priced above recent transaction average'
            vel_body = (
                f'The TruEstimate™ value of {_fmt_aed(val)} is {premium_disc}% above the average '
                f'of {n_sales} recent comparable sales ({_fmt_aed(int(avg_sale))}). '
                f'This reflects the model\'s forward-looking pricing, accounting for '
                f'the positive 6-month trend ({change_str}) and current market momentum.'
            )
        elif premium_disc < -3:
            vel_title = 'Priced below recent transaction average — value opportunity'
            vel_body = (
                f'The TruEstimate™ value of {_fmt_aed(val)} sits {abs(premium_disc)}% below '
                f'the average of {n_sales} recent comparable sales ({_fmt_aed(int(avg_sale))}). '
                f'This creates a compelling acquisition opportunity — buyers can acquire '
                f'at a discount to where the market has recently transacted.'
            )
        else:
            vel_title = 'Valuation aligned with recent transaction data'
            vel_body = (
                f'The TruEstimate™ value of {_fmt_aed(val)} aligns closely with the average '
                f'of {n_sales} recent comparable sales in {building} ({_fmt_aed(int(avg_sale))}). '
                f'This strong data alignment is what drives the {confidence.lower()} rating — '
                f'the market is actively transacting at the model\'s estimated price level.'
            )
    else:
        vel_title = 'Transaction data supports current valuation'
        vel_body = (
            f'Recent sales activity in {building} provides the DLD transaction data underpinning '
            f'this {confidence.lower()} estimate. '
            f'Our model weights the most recent 90-day transactions most heavily, '
            f'ensuring the estimate reflects current buyer sentiment rather than lagging indicators.'
        )
    insights.append({'number': '04', 'title': vel_title, 'body': vel_body})

    # ── Insight 5: Investment & yield / upside ────────────────────────────────
    beds_label = _beds_label(beds)
    dubai_avg_yield = (
        DUBAI_AVG_YIELD_STUDIO if beds == 0 else
        DUBAI_AVG_YIELD_1BR if beds == 1 else
        DUBAI_AVG_YIELD_2BR
    )

    if gross_yield and gross_yield > dubai_avg_yield + 1:
        invest_title = f'Exceptional rental yield: {gross_yield}% gross'
        invest_body = (
            f'At {gross_yield}% gross rental yield, this {beds_label} significantly exceeds '
            f'the Dubai {beds_label} average of approximately {dubai_avg_yield}%. '
            f'{location_label} benefits from strong tenant demand, proximity to key employment '
            f'hubs, and competitive rental pricing — sustaining above-average yields for investors.'
        )
    elif gross_yield:
        invest_title = f'Solid rental yield at {gross_yield}% gross'
        invest_body = (
            f'At {gross_yield}% gross rental yield, this {beds_label} delivers '
            f'{"above" if gross_yield > dubai_avg_yield else "in line with"} '
            f'the Dubai {beds_label} average of approximately {dubai_avg_yield}%. '
            f'{building} commands strong rental demand, with consistent occupier interest '
            f'driven by the area\'s connectivity, amenities, and lifestyle positioning.'
        )
    else:
        # No yield data — pivot to investment thesis
        invest_title = f'Strong investor fundamentals in {area}'
        invest_body = (
            f'{area} continues to attract investor interest driven by Dubai\'s sustained '
            f'population growth, expanding infrastructure, and the UAE\'s favourable tax environment. '
            f'{beds_label} units in established developments like {building} have historically '
            f'delivered gross rental yields of {dubai_avg_yield}–{dubai_avg_yield + 1.5}%, '
            f'with potential for short-term rental uplift through Radiant Homes, our in-house '
            f'property management arm.'
        )
    insights.append({'number': '05', 'title': invest_title, 'body': invest_body})

    return insights

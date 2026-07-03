with open('mobile-app/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add CSS for tier levels after .card-event-opts styles
css_marker = "/* Game Mechanics Viewer */"
tier_css = """    .card-tier-levels {
      margin-top: 6px;
      padding-top: 6px;
      border-top: 1px dashed var(--border);
      font-size: 11px;
    }
    .card-tier-levels .tl-row {
      display: flex;
      gap: 6px;
      align-items: flex-start;
      margin-bottom: 3px;
    }
    .card-tier-levels .tl-row:last-child { margin-bottom: 0; }
    .card-tier-levels .tl-tier {
      flex-shrink: 0;
      font-weight: 600;
      min-width: 32px;
      padding: 1px 5px;
      border-radius: 3px;
      text-align: center;
      font-size: 10px;
    }
    .card-tier-levels .tl-tier.tier-silver { background: #b0b8c833; color: #b0b8c8; }
    .card-tier-levels .tl-tier.tier-gold { background: #d4a84433; color: #d4a844; }
    .card-tier-levels .tl-tier.tier-diamond { background: #6ec6e633; color: #6ec6e6; }
    .card-tier-levels .tl-tier.tier-legendary { background: #c850f033; color: #c850f0; }
    .card-tier-levels .tl-attrs {
      color: var(--text2);
      line-height: 1.4;
    }
    .card-tier-levels .tl-attrs b { color: var(--accent2); font-weight: 600; }

    /* Game Mechanics Viewer */"""

content = content.replace(css_marker, tier_css)

# 2. Add JS to render tier levels - insert after tooltipHtml rendering
js_marker = "const attrHtml = Object.entries(attrs).slice(0, 6)"
tier_js = """// Render tier levels
        const tierLevels = f(card, '品质层级') || {};
        let tierHtml = '';
        const tierEntries = Object.entries(tierLevels).filter(([_, v]) => {
          const changes = v['属性变更'];
          return changes && changes !== '无变更' && typeof changes === 'object';
        });
        if (tierEntries.length) {
          const tierClassMap = {'银':'tier-silver','金':'tier-gold','钻石':'tier-diamond','传说':'tier-legendary','Bronze':'tier-bronze','Silver':'tier-silver','Gold':'tier-gold','Diamond':'tier-diamond','Legendary':'tier-legendary'};
          tierHtml = `<div class="card-tier-levels">${tierEntries.map(([tName, tData]) => {
            const changes = tData['属性变更'];
            const cls = tierClassMap[tName] || '';
            const attrsStr = Object.entries(changes).map(([k,v]) => `${k}: <b>${v}</b>`).join(', ');
            return `<div class="tl-row"><span class="tl-tier ${cls}">${tName}</span><span class="tl-attrs">${attrsStr}</span></div>`;
          }).join('')}</div>`;
        }
        const attrHtml = Object.entries(attrs).slice(0, 6)"""

content = content.replace(js_marker, tier_js)

# 3. Add ${tierHtml} in the card template, after tooltipHtml
old_template = "${tooltipHtml ? `<div class=\"card-tooltip\">${tooltipHtml}</div>` : ''}"
new_template = """${tooltipHtml ? `<div class="card-tooltip">${tooltipHtml}</div>` : ''}
      ${tierHtml}"""
content = content.replace(old_template, new_template)

with open('mobile-app/index.html', 'w', encoding='utf-8') as f:
    f.write(content)
print("OK - added tier levels display")

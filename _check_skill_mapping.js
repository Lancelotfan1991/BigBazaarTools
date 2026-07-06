const fs = require('fs')
const dataDir = 'e:\\Test\\bazaar-vue\\public\\data'
const heroes = ['Vanessa','Dooley','Pygmalien','Mak','Stelle','Karnok','Jules','Common','All']
const skillMap = new Map()

for (const h of heroes) {
  const fp = dataDir + '/' + h + '.json'
  if (!fs.existsSync(fp)) continue
  const d = JSON.parse(fs.readFileSync(fp, 'utf-8'))
  const skills = d['技能'] || []
  skills.forEach(s => {
    const en = s['英文名'] || ''
    const zh = s['名称'] || ''
    if (en && zh) skillMap.set(en, zh)
  })
}
console.log('Hero skill map size:', skillMap.size)

const md = JSON.parse(fs.readFileSync(dataDir + '/monsters.json', 'utf-8'))
const items = md['物品'] || []
const monsterSkills = new Set()
items.forEach(m => {
  const s = (m['怪物信息'] || {})['技能'] || []
  s.forEach(sk => monsterSkills.add(sk['名称']))
})
console.log('Unique monster skills:', monsterSkills.size)

let matched = 0, unmatched = []
for (const sk of monsterSkills) {
  if (skillMap.has(sk)) {
    matched++
    console.log(`  ${sk} -> ${skillMap.get(sk)}`)
  } else {
    unmatched.push(sk)
  }
}
console.log(`\nMatched: ${matched}, Unmatched: ${unmatched.length}`)
console.log('Unmatched:', unmatched.join(', '))

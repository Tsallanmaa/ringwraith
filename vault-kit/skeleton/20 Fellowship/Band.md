---
type: band
readiness: 4
burden: medium            # light | medium | heavy | overburdened
dispositions:
  expertise: 2
  manoeuvre: 2
  rally: 2
  vigilance: 2
  war: 2
shared_calling: ""
weary: false
---

# The Band

*Readiness TN = 20 − Readiness. Dispositions above are the defaults; each mission's composition
adjusts them (see the mission note).*

## Roster
```base
filters:
  and:
    - 'file.inFolder("20 Fellowship/Allies")'
    - 'type != "index"'
views:
  - type: table
    name: Roster
    order:
      - file.name
      - note.gift
      - note.status
      - note.injury
      - note.fatigue
      - note.hardened
    sort:
      - property: file.name
        direction: ASC
  - type: cards
    name: Portraits
    image: note.image
    cardSize: 160
    order:
      - file.name
      - note.gift
      - note.status
    sort:
      - property: file.name
        direction: ASC
```

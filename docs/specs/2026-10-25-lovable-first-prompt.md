# Lovable first prompt

The owner creates the Lovable project `quacks-frontend`, pastes the text below as its first prompt, then connects the project to GitHub. Spec: `docs/specs/2026-10-25-rule-fixes-and-brew-screen.md`.

The kick-off part keeps this first message small: Lovable sets up the project and reads the brief, and builds no game screen yet. The brew screen is built later from a `Lane: frontend` issue in the normal loop, which sends the brief again as its goal.

---

**Kick-off (do only this now).** Below is the brief for the whole first screen, so you know where we are going. In this first message, do not build the screen yet. Only:

1. Set up the project `quacks-frontend` (React, TypeScript, Tailwind).
2. Create the base theme from "Look and feel" below: pixel font, palette (including the chip colours white, orange, green, blue, red, black, yellow, purple), pixel borders, dark background.
3. Create one empty start page with the title "Quacks" in that theme.
4. Reply with a short plan of how you would build the brew screen from the brief: the components, the pot layout module, and where the data access lives. Do not implement it.

The game rules will be added to the project knowledge. We send the screens as separate requests later.

**The brief**

Build **quacks-frontend**, the browser frontend of our implementation of the board game "The Quacks of Quedlinburg" for two players, with the ingredient chips of the first spellbook. The game rules run in a separate local Python service; this app only shows the game and sends the player's choices. Put no game rules in the app.

**Look and feel.** Retro pixel art. Dark, alchemist, witchcraft practised in a cellar, but at the same time warm and playful. No real horror. Crisp pixel fonts and pixel borders, a limited palette with glowing accents for the chip colours. Show no text that is not about a game component: no flavour texts, no jokes.

**The heart: the cauldron (the pot).** The pot is a track of 54 fields (0 to 53). Lay it out as a square "snake" spiral of pixel tiles that starts in the centre (field 0) and runs counter-clockwise to the outside. Each placed chip fills every field it moved over with its colour (from its first covered field to its landing field), and the landing field gets a clear outline and shows the chip value. Keep the spiral shape replaceable: put the geometry in one "pot layout" module that maps each field number to its position and outline, and make the rest of the pot (cell fills, landing outline, lighting, darkness, animations) work on those outlines without knowing the shape. A second layout (irregular Voronoi-like cells, still spiralling outwards) will be added later and switched with a toggle. The next 11 fields from the current scoring field are lit and show their money, points and a ruby mark when the field has one. Every other field is grey or dark, as if hidden in the gloom.

**Around the pot:** round (for example 3/9) and the round card, the player's points, money, rubies, flask (full or empty), droplet and start field, and an explosion meter (white total against the explosion limit). **The bag:** the chips still in the bag as coloured pixel dots with their value. **Buttons:** big "Draw" and "Stop" buttons, and "Use flask" and "Card 17" when they are offered; keyboard keys d, s, f, u. **Blue hand:** a blue chip can give the player a hand of chips to choose from; show them as selectable chips (the `play:<slot>` actions in `legal`) with "put all back and Draw" and "put all back and Stop" buttons. Any action in `legal` that has no control of its own on the screen is shown as a plain button with its label, so the player can always act.

**Other players:** each other player gets a smaller panel of the same kind (their pot, bag, points, status) that can be enlarged. Other players' pots show only their placed chips: the lit look-ahead window (`window` in the data) belongs to the viewing player only. Build the layout from a list of players, not a fixed pair: three or four players must fit later.

**Animations:** a drawn chip drops into the cauldron and lands with a small pixel splash; an explosion gets a big puff of smoke.

`explosion_limit` is the limit in effect this round (round card effects are already included); the app does no rule arithmetic.

**For now, use the sample state below** as a fixed mock, so the screen can be built before the service is connected. Keep the data access in one small module so it can later call the service at a configurable base URL (default `http://localhost:8000`).

Sample state (the shape the service will send; the chip list is an excerpt, the real game has 19 chip types in 8 colours: white, orange, green, blue, red, black, yellow, purple):

```json
{
  "game": {"round": 3, "rounds": 9, "phase": "brew", "revision": 12, "explosion_limit": 9,
           "card": {"id": "card_4", "effect": "explosion_limit_plus_2", "text": "explosion limit +2 this round"}},
  "you": "p1",
  "to_act": ["p1", "p2"],
  "chips": [
    {"id": "white_1", "colour": "white", "value": 1}, {"id": "white_2", "colour": "white", "value": 2},
    {"id": "white_3", "colour": "white", "value": 3}, {"id": "orange_1", "colour": "orange", "value": 1},
    {"id": "green_1", "colour": "green", "value": 1}, {"id": "green_2", "colour": "green", "value": 2},
    {"id": "blue_2", "colour": "blue", "value": 2},
    {"id": "yellow_2", "colour": "yellow", "value": 2}, {"id": "black_1", "colour": "black", "value": 1},
    {"id": "purple_1", "colour": "purple", "value": 1}, {"id": "red_1", "colour": "red", "value": 1}
  ],
  "seats": [
    {"seat": "p1", "kind": "human", "status": "brewing", "points": 7, "money": 0, "rubies": 2,
     "flask_full": true, "white_total": 3, "droplet": 2, "start_field": 3, "rat_tail": 1,
     "bag": {"white_1": 3, "white_2": 1, "orange_1": 1, "green_1": 1},
     "pot": [
       {"chip": "orange_1", "colour": "orange", "value": 1, "from": 4, "landing": 4},
       {"chip": "white_2", "colour": "white", "value": 2, "from": 5, "landing": 6},
       {"chip": "green_2", "colour": "green", "value": 2, "from": 7, "landing": 8},
       {"chip": "white_1", "colour": "white", "value": 1, "from": 9, "landing": 9}
     ]},
    {"seat": "p2", "kind": "bot:random", "status": "stopped", "points": 9, "money": 0, "rubies": 1,
     "flask_full": false, "white_total": 5, "droplet": 1, "start_field": 1, "rat_tail": 0,
     "bag": {"white_1": 2, "white_2": 1, "orange_1": 1, "green_1": 1, "blue_2": 1},
     "pot": [
       {"chip": "white_3", "colour": "white", "value": 3, "from": 2, "landing": 4},
       {"chip": "green_1", "colour": "green", "value": 1, "from": 5, "landing": 5},
       {"chip": "white_2", "colour": "white", "value": 2, "from": 6, "landing": 7}
     ]}
  ],
  "window": [
    {"field": 10, "money": 10, "points": 2, "ruby": false}, {"field": 11, "money": 11, "points": 2, "ruby": false},
    {"field": 12, "money": 12, "points": 2, "ruby": false}, {"field": 13, "money": 13, "points": 2, "ruby": true},
    {"field": 14, "money": 14, "points": 3, "ruby": false}, {"field": 15, "money": 15, "points": 3, "ruby": false},
    {"field": 16, "money": 15, "points": 3, "ruby": true}, {"field": 17, "money": 16, "points": 3, "ruby": false},
    {"field": 18, "money": 16, "points": 4, "ruby": false}, {"field": 19, "money": 17, "points": 4, "ruby": false},
    {"field": 20, "money": 17, "points": 4, "ruby": true}
  ],
  "legal": [
    {"id": "draw", "label": "draw"}, {"id": "stop", "label": "stop"},
    {"id": "use_flask", "label": "flask: last white chip back to bag"}
  ],
  "hand": [],
  "log": ["p1: draw  draw_chip chip=white_1", "p2: stop"]
}
```

When we ask for it, build this one screen well: the cauldron spiral, the panels around it, the bag, the buttons and the two animations. Other game phases come later.

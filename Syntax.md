# SwatLLM Commands Syntax

This mod reads exactly one command line from `commands.txt` and executes it in game.
After successful reading, the mod empties the `commands.txt` file immediately.

## Hotkeys (In-Game)
- **`L`**: Saves the exact `X Y Z` coordinates of whatever your crosshair is pointing at (floor, wall, door) into the mod's memory. The UE4SS console will log the coordinates.
- **`P`**: Executes customized commands on the `X Y Z` coordinates you just saved with `L`. You can set what this hotkey does by editing `config.txt`. The mod reloads `config.txt` every time you press `P`, so you can change the hotkey behavior mid-game without restarting!

## config.txt Configuration

The `config.txt` file lets you set up to two commands that will be fired off simultaneously when pressing `P` (e.g., to send RED and BLUE teams to do different things).

Example `config.txt`:
```
P_COMMAND_1=RED MOVE
P_COMMAND_2=BLUE BREACH
```

If you only want one command, set the second one to `NONE`:
```
P_COMMAND_1=GOLD STACK_UP
P_COMMAND_2=NONE
```

## commands.txt Format

You can specify a team (optional), a command, and optional `X Y Z` absolute coordinates. If no team is specified, the command applies to `GOLD` team.
Teams: `RED`, `BLUE`, `GOLD`

Syntax: `[TEAM] COMMAND [X] [Y] [Z]`

### New Commands

- `GET_DOORS`
  Exports all unique doors in the current level and their exact `X Y Z` coordinates to `doors.txt` (located in the same mod folder).

### Existing Commands (with optional coordinates)

- `MOVE [X] [Y] [Z]`
  (Team moves to coordinates. If no coordinates, they move to where you are aiming)
  Example: `BLUE MOVE 1200 -550 120`

- `COVER [X] [Y] [Z]`
  (Team moves to coordinates and covers the area)
  Example: `RED COVER 1200 -550 120`

- `OPEN_DOOR [X] [Y] [Z]`
  (Team opens the nearest door to the `X Y Z` coordinates. If no coordinates, opens the door nearest to you)
  Example: `OPEN_DOOR 500 200 50`

- `BREACH [X] [Y] [Z]`
  (Team breaches nearest door to coordinates)
  Example: `RED BREACH 500 200 50`

- `STACK_UP [X] [Y] [Z]`
  (Team stacks up on nearest door to coordinates)
  Example: `BLUE STACK_UP 500 200 50`

- `FALL_IN`
  (Team follows you)

- `SEARCH_AND_SECURE`
  (Team searches the current area)

- `HOLD`
  (Team holds position)

- `RESTRAIN`
  (Team restrains the target you are aiming at)

- `YELL`
  (You yell for compliance)

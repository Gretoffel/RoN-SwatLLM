## 1. Grundphilosophie
- keine Koordinaten an das LLM senden.
- nur relative Positions-Beschreibungen (relativ zur Blickrichtung des Spielers/Teamleaders).
- Single-Call-System: 
	- Ein einziger LLM-Call verarbeitet beide Teams (Rot & Blau) gleichzeitig ("Gold Commander" Prinzip)
	- Es wird nur 1 Raum pro Team pro LLM-Call abgearbeitet und protokolliert (siehe folgende punkte)
- LLM schreibt eine Liste "done" und ein "new_objective" (Stille-Post-Prinzip für das Gedächtnis beim Raumwechsel).
- LLM prüft, ob "done" + die aktuell vergebenen Befehle den initialen Userprompt vollständig erfüllen -> Wenn ja, geht das Team wieder auf Standby.

## 2. Context-Teile, Parameter, ...
1. Alle Räume in denen mind. 1 Team oder der Spieler ist
	- ID: int / String (z.B. "Room_0")
	- Welches Team / welche Teams: String (z.B. "Red", "Blue", "Player")
	- Welche Türen (sichtbar): Array von Doors
2. Doors:
	- ID: int / String (z.B. "door_01")
	- Relative Position: String (z.B. "Front (Left)")
	- distance: float (in Metern)
	- isOpen: bool
	- isLocked: bool
	- isDoubleDoor: bool
	- ? wedged: bool (maybe later when the base system is done)
	- ? type: String (wood, metal, glass - maybe later when the base system is done)

## 3. Relative Position berechnen (Dynamisches 8-Wege-System)
- Es wird ein festes 8-Wege-System basierend auf der Blickrichtung genutzt:
	- Vorne (Front)
	- Vorne-Rechts (Front-Right)
	- Rechts (Right)
	- Hinten-Rechts (Back-Right)
	- Hinten (Back)
	- Hinten-Links (Back-Left)
	- Links (Left)
	- Vorne-Links (Front-Left)

- **Kollisions-Lösung (Dynamisches Sub-Positioning):**
	- Wenn sich mehrere Türen im selben Sektor (z.B. "Front") befinden, sortiert das Mod-Skript diese Türen nach ihrem horizontalen Winkel (Yaw-Offset) zum Fadenkreuz (von links nach rechts).
	- Das Skript hängt dann automatisch einen natürlichen Modifikator an den String an:
		- Bei 2 Türen: Tür 1 wird zu `Front (Leftmost)`, Tür 2 wird zu `Front (Rightmost)`.
		- Bei 3 Türen: `Front (Leftmost)`, `Front (Center)`, `Front (Rightmost)`.
	- **Ergebnis:** Wenn der User sagt "Breach the left door", findet das LLM direkt das Wort "Left" im String der passenden Tür. 
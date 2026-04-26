from collections import Counter
from civ_game.game import Game, PLAYER_NAMES, DIFFICULTY_DEFS
from civ_game.systems.ai_d import ai_take_turn as ai_d_take_turn  # AI D: players 2, 3 (Huns, Babylon)
from civ_game.systems.ai_e import ai_take_turn as ai_e_take_turn  # AI E: players 0, 1 (Rome, Greece)

NUM_GAMES   = 100
MAX_TURNS   = 2000  # safety cap — prevents infinite loops on rare stalemates
NUM_PLAYERS = 4

# ── difficulty config ──────────────────────────────────────────────────────────
# DIFFICULTY_DEFS is imported from game.py — edit values there.
# Set a difficulty per player (indices 0-3: Rome, Greece, Huns, Babylon)
PLAYER_DIFFICULTIES = ["prince", "prince", "prince", "prince"]

results = []

for i in range(NUM_GAMES):
    game = Game(num_players=NUM_PLAYERS, seed=i,
                cpu_flags=[True] * NUM_PLAYERS,
                difficulty_flags=PLAYER_DIFFICULTIES)

    while game.winner is None and game.turn < MAX_TURNS:
        civ = game.current_civ()
        (ai_d_take_turn if civ.player_index >= 20 else ai_e_take_turn)(game, civ)
        game.end_turn()

    results.append({"game": i + 1, "winner": game.winner, "turns": game.turn})
    winner_name = PLAYER_NAMES[game.winner] if game.winner is not None else "None"
    print(f"Game {i+1:3d}: winner={winner_name}  turns={game.turn}")

# Summary
wins = Counter(r["winner"] for r in results)
print("\n=== Summary ===")
for idx in range(NUM_PLAYERS):
    print(f"  {PLAYER_NAMES[idx]}: {wins[idx]} wins")
print(f"  Timeout (no winner): {wins[None]}")
avg = sum(r["turns"] for r in results) / len(results)
print(f"  Avg turns: {avg:.1f}")

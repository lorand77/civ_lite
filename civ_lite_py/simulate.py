from collections import Counter
from civ_game.game import Game, PLAYER_NAMES
from civ_game.systems.ai import ai_take_turn

NUM_GAMES   = 1000
MAX_TURNS   = 2000  # safety cap — prevents infinite loops on rare stalemates
NUM_PLAYERS = 4

results = []

for i in range(NUM_GAMES):
    game = Game(num_players=NUM_PLAYERS, seed=i,
                cpu_flags=[True] * NUM_PLAYERS)

    while game.winner is None and game.turn < MAX_TURNS:
        ai_take_turn(game, game.current_civ())
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

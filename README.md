
# Battleship Treasure Hunt  🎲⚓️💰

Turn the classic clue‑sharing treasure hunt into a digital, coalition‑aware party game! 3‑6 players reveal partial information, form temporary coalitions, and share loot according to their *marginal* contributions (Shapley value).

```sh
python -m pip install -r requirements.txt
python main.py
```

* **Quick‑start**: press <Enter> at the setup screen to auto‑load demo data.
* **Victory**: when all coins are claimed or the facilitator presses **End Game**, payouts are computed by Monte‑Carlo Shapley sampling (default 6000 permutations).

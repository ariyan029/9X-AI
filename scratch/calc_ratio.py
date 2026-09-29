def calculate_plan(capital, rounds, initial_bet, multiplier):
    bets = []
    total_cost = 0
    for i in range(rounds):
        if i == 0:
            bet = initial_bet
        else:
            bet = int(bets[-1] * multiplier)
            
        # Ensure profit
        if bet <= sum(bets):
            bet = sum(bets) + 1

        bets.append(bet)
        total_cost += bet
        
    return bets, total_cost

best_plans = []

for initial_bet in range(1, 100):
    for mult in [2.0, 2.1, 2.2, 2.3, 2.4, 2.5, 3.0]:
        bets, cost = calculate_plan(15000, 12, initial_bet, mult)
        if cost <= 15000:
            profits = [b * 2 - sum(bets[:i+1]) for i, b in enumerate(bets)]
            min_profit = min(profits)
            if min_profit > 0:
                best_plans.append({
                    'initial_bet': initial_bet,
                    'multiplier': mult,
                    'cost': cost,
                    'bets': bets,
                    'profits': profits
                })

# Sort by max of average profit
best_plans.sort(key=lambda x: sum(x['profits'])/len(x['profits']), reverse=True)

for plan in best_plans[:5]:
    print(f"Multiplier: {plan['multiplier']}, Initial Bet: {plan['initial_bet']}, Cost: {plan['cost']}")
    print(f"Bets: {plan['bets']}")
    print(f"Profits: {plan['profits']}")
    print("-" * 50)

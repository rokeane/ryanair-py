from datetime import datetime, timedelta

from ryanair import Ryanair

api = Ryanair(currency="EUR")
START = datetime.now().date() + timedelta(days=60)
END = START + timedelta(days=80)

cheapest_trip1 = api.get_return_flight_prices_from_weekday_combos(START, END, "Wed", "Sun", "TLS", "DUB")
cheapest_trip2 = api.get_return_flight_prices_from_weekday_combos(START, END, "Fri", "Sun", "TLS", "STN")

print("Cheapest Trip is:\n", cheapest_trip1)
print("Cheapest Trip is:\n", cheapest_trip2)

# TODO Write Error messages in case a weekday is incorrectly entered 
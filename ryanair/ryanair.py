"""
This module allows you to retrieve the cheapest flights, with or without return flights, within a fixed set of dates.
This is done directly through Ryanair's API, and does not require an API key.
"""
import logging
import sys
from datetime import datetime, date, time
from operator import attrgetter
from typing import Union, Optional

import backoff

from ryanair.SessionManager import SessionManager
from ryanair.types import Flight, Trip

logger = logging.getLogger("ryanair")
if not logger.handlers:
    logger.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s.%(msecs)03d %(levelname)s:%(message)s", datefmt="%Y-%m-%d %I:%M:%S"
    )

    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)


class RyanairException(Exception):
    def __init__(self, message):
        super().__init__(f"Ryanair API: {message}")


# noinspection PyBroadException
class Ryanair:
    BASE_SERVICES_API_URL = "https://services-api.ryanair.com/farfnd/v4/"

    def __init__(self, currency: Optional[str] = None):
        self.currency = currency

        self._num_queries = 0
        self.session_manager = SessionManager()
        self.session = self.session_manager.get_session()

    def get_cheapest_flights(
        self,
        airport: str,
        date_from: Union[datetime, date, str],
        date_to: Union[datetime, date, str],
        destination_country: Optional[str] = None,
        custom_params: Optional[dict] = None,
        departure_time_from: Union[str, time] = "00:00",
        departure_time_to: Union[str, time] = "23:59",
        max_price: Optional[int] = None,
        destination_airport: Optional[str] = None,
    ):
        query_url = "".join((Ryanair.BASE_SERVICES_API_URL, "oneWayFares"))

        params = {
            "departureAirportIataCode": airport,
            "outboundDepartureDateFrom": self._format_date_for_api(date_from),
            "outboundDepartureDateTo": self._format_date_for_api(date_to),
            "outboundDepartureTimeFrom": self._format_time_for_api(departure_time_from),
            "outboundDepartureTimeTo": self._format_time_for_api(departure_time_to),
        }
        if self.currency:
            params["currency"] = self.currency
        if destination_country:
            params["arrivalCountryCode"] = destination_country
        if max_price:
            params["priceValueTo"] = max_price
        if destination_airport:
            params["arrivalAirportIataCode"] = destination_airport
        if custom_params:
            params.update(custom_params)

        response = self._retryable_query(query_url, params)["fares"]

        if response:
            return [
                self._parse_cheapest_flight(flight["outbound"]) for flight in response
            ]

        return []

    def get_cheapest_return_flights(
        self,
        source_airport: str,
        date_from: Union[datetime, date, str],
        date_to: Union[datetime, date, str],
        return_date_from: Union[datetime, date, str],
        return_date_to: Union[datetime, date, str],
        destination_country: Optional[str] = None,
        custom_params: Optional[dict] = None,
        outbound_departure_time_from: Union[str, time] = "00:00",
        outbound_departure_time_to: Union[str, time] = "23:59",
        inbound_departure_time_from: Union[str, time] = "00:00",
        inbound_departure_time_to: Union[str, time] = "23:59",
        max_price: Optional[int] = None,
        destination_airport: Optional[str] = None,
    ):
        query_url = "".join((Ryanair.BASE_SERVICES_API_URL, "roundTripFares"))

        params = {
            "departureAirportIataCode": source_airport,
            "outboundDepartureDateFrom": self._format_date_for_api(date_from),
            "outboundDepartureDateTo": self._format_date_for_api(date_to),
            "inboundDepartureDateFrom": self._format_date_for_api(return_date_from),
            "inboundDepartureDateTo": self._format_date_for_api(return_date_to),
            "outboundDepartureTimeFrom": self._format_time_for_api(
                outbound_departure_time_from
            ),
            "outboundDepartureTimeTo": self._format_time_for_api(
                outbound_departure_time_to
            ),
            "inboundDepartureTimeFrom": self._format_time_for_api(
                inbound_departure_time_from
            ),
            "inboundDepartureTimeTo": self._format_time_for_api(
                inbound_departure_time_to
            ),
        }
        if self.currency:
            params["currency"] = self.currency
        if destination_country:
            params["arrivalCountryCode"] = destination_country
        if max_price:
            params["priceValueTo"] = max_price
        if destination_airport:
            params["arrivalAirportIataCode"] = destination_airport
        if custom_params:
            params.update(custom_params)

        response = self._retryable_query(query_url, params)["fares"]

        if response:
            return [
                self._parse_cheapest_return_flights_as_trip(
                    trip["outbound"], trip["inbound"]
                )
                for trip in response
            ]
        else:
            return []

    @staticmethod
    def _get_backoff_type():
        if "unittest" in sys.modules.keys():
            return backoff.constant(interval=0)

        return backoff.expo()

    @staticmethod
    def _on_query_error(e):
        logger.exception(f"Gave up retrying query, last exception was {e}")

    @backoff.on_exception(
        _get_backoff_type,
        Exception,
        max_tries=5,
        logger=logger,
        raise_on_giveup=True,
        on_giveup=_on_query_error,
    )
    def _retryable_query(self, url, params=None):
        self._num_queries += 1
        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def _parse_cheapest_flight(self, flight):
        currency = flight["price"]["currencyCode"]
        if self.currency and self.currency != currency:
            logger.warning(
                f"Requested cheapest flights in {self.currency} but API responded with fares in {currency}"
            )
        return Flight(
            origin=flight["departureAirport"]["iataCode"],
            originFull=", ".join(
                (
                    flight["departureAirport"]["name"],
                    flight["departureAirport"]["countryName"],
                )
            ),
            destination=flight["arrivalAirport"]["iataCode"],
            destinationFull=", ".join(
                (
                    flight["arrivalAirport"]["name"],
                    flight["arrivalAirport"]["countryName"],
                )
            ),
            departureTime=datetime.fromisoformat(flight["departureDate"]),
            flightNumber=f"{flight['flightNumber'][:2]} {flight['flightNumber'][2:]}",
            price=flight["price"]["value"],
            currency=currency,
        )

    def _parse_cheapest_return_flights_as_trip(self, outbound, inbound):
        outbound = self._parse_cheapest_flight(outbound)
        inbound = self._parse_cheapest_flight(inbound)

        return Trip(
            outbound=outbound,
            inbound=inbound,
            totalPrice=inbound.price + outbound.price,
        )

    @staticmethod
    def _format_date_for_api(d: Union[datetime, date, str]):
        if isinstance(d, str):
            return d

        if isinstance(d, datetime):
            return d.date().isoformat()

        if isinstance(d, date):
            return d.isoformat()

    @staticmethod
    def _format_time_for_api(t: Union[time, str]):
        if isinstance(t, str):
            return t

        if isinstance(t, time):
            return t.strftime("%H:%M")

    @property
    def num_queries(self) -> __init__:
        return self._num_queries
    
    # get all possible return flights for a given time period
    # based on which weekday that you wish to depart
    # and which weekday that you wish to return
    def get_return_flight_prices_from_weekday_combos(        
        self,
        date_from: Union[datetime, date, str],
        date_to: Union[datetime, date, str],
        weekday_from: str,
        weekday_to: str,
        source_airport: str,
        destination_airport: Optional[str],
        ):
        # get list of return flights from weekday_from to weekday_to from source to destination 
        results = []
        # get the list of dates that we want to put into our get cheapest flights function
        getaway_return_dates = self.get_getaway_dates(date_from, date_to, weekday_from, weekday_to)

        for start, end in getaway_return_dates:
            flight = self.get_cheapest_return_flights(
                    source_airport,
                    start,
                    start,
                    end,
                    end,
                    destination_airport=destination_airport
                )
            if(flight):
                results.append(flight[0])

        cheapest_trip = min(results,key=attrgetter('totalPrice'))

        return cheapest_trip
        
#   write function that gets the dates from all of one day of the week
#   between one date and another
#   return an array of dates corresponding to every weekday
    def get_getaway_dates(self, date_from: date, date_to: date, weekday_from: str, weekday_to: str):

        weekdays = ["Mon","Tues","Wed","Thurs","Fri","Sat","Sun"]

        results = []

        # find which day in the year the date is
        start_date = date_from.toordinal()
        start_weekday = date_from.weekday()
        end_date = date_to.toordinal()

        first_date = weekdays.index(weekday_from) - start_weekday + start_date
        if weekdays.index(weekday_from) < start_weekday:
            first_date += 7  

        last_date = weekdays.index(weekday_to) - start_weekday + start_date
        if weekdays.index(weekday_to) < start_weekday:
            last_date += 7 

        if last_date < first_date:
            last_date += 7

        while (last_date <= end_date):

            # get first dates of startweekday and endweekday -> convert both from ordinal back to gregorian calendar
            getaway = (date.fromordinal(first_date), date.fromordinal(last_date))

            results.append(getaway)

            first_date += 7
            last_date += 7

        
        return results





"""How the dashboard is cut into sections and groups."""

import unittest

from . import support
from resources.lib import sections

# The frontend's DEFAULT_SUMMARY_KEYS, in its order.
DEFAULTS = ("light", "climate", "security", "media_players", "maintenance",
            "weather", "energy")


def house(extra_entities=(), extra_states=(), home=None, energy=None):
    entities = [
        support.entity("light.decke", "Deckenlampe", device_id="dev_lamp"),
        support.entity("binary_sensor.fenster", "Fenster", device_id="dev_sensor",
                       device_class="window"),
        support.entity("sensor.kueche_temperatur", "Temperatur", area_id="kueche",
                       device_class="temperature"),
        support.entity("sensor.cpu", "CPU Temperatur", area_id="kueche",
                       device_class="temperature"),
        support.entity("sensor.batterie", "Batterie", device_id="dev_sensor",
                       device_class="battery", category="diagnostic"),
        support.entity("lock.tuer", "Schloss", area_id="flur_ug"),
    ]
    states = [
        support.state("light.decke", "off"),
        support.state("binary_sensor.fenster", "on"),
        support.state("sensor.kueche_temperatur", "21.5"),
        support.state("sensor.cpu", "48"),
        support.state("sensor.batterie", "94"),
        support.state("lock.tuer", "locked"),
    ]
    return support.build(
        entities=list(entities) + list(extra_entities),
        states=list(states) + list(extra_states),
        devices=support.DEVICES, areas=support.AREAS, floors=support.FLOORS,
        home=home, energy=energy)


class AreaSections(unittest.TestCase):
    def test_groups_by_device_and_collects_the_rest(self):
        store = house()
        built = {s.key: s for s in sections.build(store, translate=support.untranslated)}
        kitchen = built["area:kueche"]

        self.assertEqual([g.title for g in kitchen.groups],
                         ["Fenstersensor", "no_device"])
        # The battery is diagnostic, so it belongs to maintenance, not here.
        self.assertEqual(kitchen.groups[0].entity_ids, ["binary_sensor.fenster"])
        self.assertEqual(sorted(kitchen.groups[1].entity_ids),
                         ["sensor.cpu", "sensor.kueche_temperatur"])

    def test_a_devices_entities_stand_by_doing_then_kind_then_name(self):
        """What can be acted on first, and each kind together within that."""
        store = house(
            extra_entities=[
                support.entity("automation.zzz", "Zuletzt", device_id="dev_sensor"),
                support.entity("automation.aaa", "Anfang", device_id="dev_sensor"),
                support.entity("switch.mitte", "Mitte", device_id="dev_sensor"),
            ],
            extra_states=[
                support.state("automation.zzz", "on"),
                support.state("automation.aaa", "on"),
                support.state("switch.mitte", "off"),
            ])
        built = {s.key: s for s in sections.build(store, translate=support.untranslated)}
        sensor = built["area:kueche"].groups[0]
        # The binary sensor only reports, so it falls behind the switch even
        # though its kind sorts ahead of one.
        self.assertEqual(sensor.entity_ids,
                         ["automation.aaa", "automation.zzz", "switch.mitte",
                          "binary_sensor.fenster"])

    def test_floors_and_rooms_keep_registry_order(self):
        store = house()
        options = sections.Options(hide_empty_areas=False)
        areas = [s for s in sections.build(store, options, translate=support.untranslated)
                 if s.kind == sections.AREA]
        self.assertEqual([(s.subtitle, s.title) for s in areas],
                         [("Keller", "Kellervorraum"), ("Keller", "Flur UG"),
                          ("Erdgeschoss", "Küche"), ("", "Mobile Geräte")])

    def test_empty_rooms_can_be_hidden(self):
        store = house()
        options = sections.Options(hide_empty_areas=True)
        titles = [s.title for s in sections.build(store, options, translate=support.untranslated)]
        self.assertNotIn("Mobile Geräte", titles)


class Summaries(unittest.TestCase):
    def summary(self, key, **kwargs):
        home = {"shortcuts": [{"type": "summary", "key": key}]}
        store = house(home=home, **kwargs)
        return next(s for s in sections.build(store, translate=support.untranslated) if s.key == key)

    def test_room_headings_carry_the_floor(self):
        security = self.summary("security")
        self.assertEqual([g.title for g in security.groups],
                         ["Keller  -  Flur UG", "Erdgeschoss  -  Küche"])

    def test_climate_takes_the_rooms_own_sensors_only(self):
        climate = self.summary("climate")
        # sensor.cpu is a temperature too, but no room is measured by it.
        self.assertEqual(climate.entity_ids, ["sensor.kueche_temperatur"])

    def test_maintenance_lists_batteries_at_any_level(self):
        maintenance = self.summary("maintenance")
        self.assertEqual(maintenance.entity_ids, ["sensor.batterie"])

    def test_media_players_are_a_summary_of_their_own(self):
        players = self.summary(
            "media_players",
            extra_entities=[support.entity("media_player.tv", "Fernseher",
                                           area_id="kueche")],
            extra_states=[support.state("media_player.tv", "playing")])
        self.assertEqual(players.entity_ids, ["media_player.tv"])
        self.assertEqual(players.title, "media_players")

    def keys(self, shortcuts, **kwargs):
        """The summaries shown, in a house that has something for every one."""
        kwargs.setdefault("extra_entities", [
            support.entity("media_player.tv", "Fernseher", area_id="kueche"),
            support.entity("weather.home", "Wetter")])
        kwargs.setdefault("extra_states", [
            support.state("media_player.tv", "playing"),
            support.state("weather.home", "sunny"),
            support.state("sensor.netz", "1024")])
        kwargs.setdefault("energy", {"energy_sources": [
            {"type": "grid", "stat_energy_from": "sensor.netz"}]})
        store = house(home={} if shortcuts is None else {"shortcuts": shortcuts},
                      **kwargs)
        return [s.key for s in sections.build(store, translate=support.untranslated)
                if s.kind == sections.SUMMARY]

    def test_a_shortcut_that_is_not_a_summary_is_passed_over(self):
        self.assertEqual(self.keys([{"type": "entity", "entity_id": "light.decke"}]),
                         list(DEFAULTS))

    def test_nothing_saved_is_every_summary_in_home_assistants_order(self):
        self.assertEqual(self.keys(None), list(DEFAULTS))

    def test_the_saved_order_leads_and_the_rest_follow(self):
        self.assertEqual(self.keys([{"type": "summary", "key": "energy"},
                                    {"type": "summary", "key": "light"}]),
                         ["energy", "light", "climate", "security", "media_players",
                          "maintenance", "weather"])

    def test_unknown_and_repeated_summaries_drop_out(self):
        self.assertEqual(self.keys([{"type": "summary", "key": "light"},
                                    {"type": "summary", "key": "alerts"},
                                    {"type": "summary", "key": "light"}]),
                         list(DEFAULTS))

    def test_a_summary_with_nothing_to_show_is_left_out(self):
        self.assertNotIn("media_players", self.keys(None, extra_entities=[],
                                                    extra_states=[]))

    def test_the_sun_alone_makes_no_weather(self):
        self.assertNotIn("weather", self.keys(
            None, extra_entities=[support.entity("sun.sun", "Sonne")],
            extra_states=[support.state("sun.sun", "above_horizon")]))

    def test_energy_needs_the_grid_to_be_drawn_from(self):
        solar = {"energy_sources": [{"type": "solar", "stat_energy_from": "sensor.netz"}]}
        self.assertNotIn("energy", self.keys(None, energy=solar))
        self.assertIn("energy", self.keys(None))

    def test_maintenance_needs_a_battery_not_just_an_update(self):
        store = support.build(
            entities=[support.entity("update.router", "Router")],
            states=[support.state("update.router", "on")])
        self.assertEqual([s.key for s in sections.build(store, translate=support.untranslated)
                          if s.kind == sections.SUMMARY], [])

    def test_a_summary_can_be_built_while_an_entity_appears(self):
        store = house(home={"shortcuts": [{"type": "summary", "key": "light"}]})
        is_visible = store.is_visible

        def arriving(entity_id, include_diagnostic=False):
            # What the reader thread may do between two steps of the walk.
            store._on_state_changed({"data": {
                "entity_id": "light.neu", "new_state": support.state("light.neu", "on")}})
            return is_visible(entity_id, include_diagnostic)

        store.is_visible = arriving
        light = next(s for s in sections.build(store, translate=support.untranslated)
                     if s.key == "light")
        self.assertEqual(light.entity_ids, ["light.decke"])

    def test_hidden_shortcuts_are_skipped(self):
        self.assertEqual(self.keys([{"type": "summary", "key": "light", "hidden": True}]),
                         list(DEFAULTS[1:]))


class Favourites(unittest.TestCase):
    def test_order_is_left_as_home_assistant_holds_it(self):
        order = ["lock.tuer", "light.decke", "binary_sensor.fenster"]
        store = house(home={"favorite_entities": order})
        favourites = next(s for s in sections.build(store, translate=support.untranslated)
                          if s.kind == sections.FAVOURITES)
        self.assertEqual(favourites.entity_ids, order)
        self.assertEqual([g.title for g in favourites.groups], [""])

    def test_entities_that_are_gone_drop_out(self):
        store = house(home={"favorite_entities": ["light.decke", "light.weg"]})
        favourites = next(s for s in sections.build(store, translate=support.untranslated)
                          if s.kind == sections.FAVOURITES)
        self.assertEqual(favourites.entity_ids, ["light.decke"])


if __name__ == "__main__":
    unittest.main()

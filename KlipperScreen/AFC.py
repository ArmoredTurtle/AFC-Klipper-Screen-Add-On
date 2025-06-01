# Armored Turtle Automated Filament Control
#
# Copyright (C) 2024-2025 Armored Turtle
#
# This file may be distributed under the terms of the GNU GPLv3 license.

import logging
import os.path
import gi
import pathlib
import re

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GdkPixbuf, Pango, GLib
from ks_includes.screen_panel import ScreenPanel
from ks_includes.KlippyRest import KlippyRest
from ks_includes.widgets.autogrid import AutoGrid
from ks_includes.widgets.keypad import Keypad
from ks_includes.KlippyGtk import find_widget
from panels import extrude
from datetime import datetime

UNLOADED = "unloaded"
PREP_NOT_LOAD = "prep not load"
LOAD_NOT_PREP = "load not prep"
LOADED = "loaded"
TOOLED = "tooled"

SYSTEM_TYPE_ICONS = {
    "Box_Turtle": "box_turtle_colored_logo.svg",
    "'Box Turtle'": "box_turtle_colored_logo.svg",
    "HTLF": "HTLF.svg",
    "'HTLF'": "HTLF.svg",
    "Night_Owl": "Night_Owl.svg",
    "'NightOwl'": "Night_Owl.svg",
}

class AFCsystem:
    def __init__(self, current_load, num_units, num_lanes, num_extruders, spoolman, current_toolchange, number_of_toolchanges, extruders, hubs, buffers):
        self.current_load = current_load
        self.num_units = num_units
        self.num_lanes = num_lanes
        self.num_extruders = num_extruders
        self.spoolman = spoolman
        self.current_toolchange = current_toolchange
        self.number_of_toolchanges = number_of_toolchanges
        self.extruders = extruders
        self.hubs = hubs
        self.buffers = buffers

class Extruder:
    def __init__(self, tool_stn, tool_stn_unload, tool_sensor_after_extruder, tool_unload_speed, tool_load_speed, buffer, lane_loaded, tool_start, tool_start_status, tool_end, tool_end_status, lanes):
        self.tool_stn = tool_stn
        self.tool_stn_unload = tool_stn_unload
        self.tool_sensor_after_extruder = tool_sensor_after_extruder
        self.tool_unload_speed = tool_unload_speed
        self.tool_load_speed = tool_load_speed
        self.buffer = buffer
        self.lane_loaded = lane_loaded
        self.tool_start = tool_start
        self.tool_start_status = tool_start_status
        self.tool_end = tool_end
        self.tool_end_status = tool_end_status
        self.lanes = lanes

class Hub:
    def __init__(self, state, cut, cut_cmd, cut_dist, cut_clear, cut_min_length, cut_servo_pass_angle, cut_servo_clip_angle, cut_servo_prep_angle, lanes, afc_bowden_length):
        self.state = state
        self.cut = cut
        self.cut_cmd = cut_cmd
        self.cut_dist = cut_dist
        self.cut_clear = cut_clear
        self.cut_min_length = cut_min_length
        self.cut_servo_pass_angle = cut_servo_pass_angle
        self.cut_servo_clip_angle = cut_servo_clip_angle
        self.cut_servo_prep_angle = cut_servo_prep_angle
        self.lanes = lanes
        self.afc_bowden_length = afc_bowden_length

class Buffer:
    def __init__(self, state, lanes, enabled, belay=None):
        self.state = state
        self.lanes = lanes
        self.enabled = enabled
        self.belay = belay

class AFCunit:
    def __init__(self, name, lanes, system_type):
        self.name = name
        self.lanes = lanes
        self.system_type = system_type

class AFClane:
    def __init__(self, name, unit, lane_data):
        self.name = name
        self.unit = unit
        self.reinit(lane_data)

    def reinit(self, lane_data):
        self.hub = lane_data.get("hub")
        self.extruder = lane_data.get("extruder")
        self.buffer = lane_data.get("buffer")
        self.buffer_status = lane_data.get("buffer_status")
        self.lane = int(lane_data.get("lane", 0))
        self.map = lane_data.get("map")
        self.load = bool(lane_data.get("load", False))
        self.prep = bool(lane_data.get("prep", False))
        self.tool_loaded = bool(lane_data.get("tool_loaded", False))
        self.loaded_to_hub = bool(lane_data.get("loaded_to_hub", False))
        self.material = lane_data.get("material")
        self.spool_id = int(lane_data.get("spool_id", 0) or 0)
        self.color = lane_data.get("color")
        self.weight = round(float(lane_data.get("weight", 0) or 0))
        self.extruder_temp = lane_data.get("extruder_temp")
        self.runout_lane = lane_data.get("runout_lane")
        self.filament_status = lane_data.get("filament_status")
        self.filament_status_led = lane_data.get("filament_status_led")
        self.lane_status = None

    def __repr__(self):
        return (f"Lane({self.name}, {self.lane}, {self.material}, {self.status}, "
                f"Load={self.load}, Prep={self.prep})")

    def icon(self, width=64, height=64):
        if not hasattr(self, '_icon') or self._icon is None:
            klipperscreendir = pathlib.Path(__file__).parent.resolve().parent
            spool_icon_path = "/path/to/spool.svg"
            if not os.path.isfile(spool_icon_path):
                spool_icon_path = os.path.join(
                    klipperscreendir, "afc_icons", "FilamentReelIcon.svg"
                )
            with open(spool_icon_path, 'r') as f:
                spool_icon_svg = f.read()

            weight = self.weight or 1000
            if self.weight is None:
                weight = 1000
            max_weight = 1000

            # --- SCALE FUNCTION ---
            min_fill_ratio = 0.29
            norm = min(max(weight / max_weight, 0), 1)
            scaled_ratio = min_fill_ratio + (1 - min_fill_ratio) * (norm ** 0.6)

            total_height = 499.8
            scale_y = scaled_ratio
            translate_y = (1 - scale_y) * total_height / 2

            transform_group = f'<g id="scaled_filament" transform="translate(0,{translate_y}) scale(1,{scale_y})">'

            # Remove old clip-paths if any
            spool_icon_svg = re.sub(r'clip-path="url\(#.*?\)"', '', spool_icon_svg)

            # Determine fill color or transparency
            if weight == 0:
                fill_style = 'fill: transparent'
            else:
                color = self.color or "#000000B3"
                fill_style = f'fill: {color}'

            # Replace style in filament_base and apply transform
            spool_icon_svg = re.sub(
                r'(<path[^>]+id="filament_base"[^>]+)style="[^"]+"',
                rf'\1style="{fill_style}"',
                spool_icon_svg
            )
            spool_icon_svg = re.sub(
                r'(<path[^>]+id="filament_base"[^>]*?/?>)',
                rf'{transform_group}\1</g>',
                spool_icon_svg
            )

            # Add xmlns if missing
            if "<svg" in spool_icon_svg and "xmlns=" not in spool_icon_svg:
                spool_icon_svg = spool_icon_svg.replace(
                    "<svg", "<svg xmlns='http://www.w3.org/2000/svg'", 1
                )

            loader = GdkPixbuf.PixbufLoader()
            try:
                loader.write(spool_icon_svg.encode())
                loader.close()
                pixbuf = loader.get_pixbuf()
                self._icon = pixbuf.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR)
            except GLib.Error as e:
                logging.error(f"Failed to load SVG: {e}")
                self._icon = None
        return self._icon




class Panel(ScreenPanel):
    apiClient: KlippyRest
    lane_widgets: dict

    def __init__(self, screen, title):
        title = title or ("AFC Status")
        super().__init__(screen, title)
        self.apiClient = screen.apiclient
        self.lane_widgets = {}
        AFClane.theme_path = screen.theme
        logging.info(f"Theme path: {AFClane.theme_path}")
        klipperscreendir = pathlib.Path(__file__).parent.resolve().parent
        self.image_path = os.path.join(
            klipperscreendir, "afc_icons")
        self.theme_path = os.path.join(
            klipperscreendir, "styles", AFClane.theme_path, "style.css")

        self.reset_ui()

        result = self.apiClient.post_request("printer/afc/status", json={})

        afc_data = result.get('result', {}).get('status:', {}).get('AFC', {})
        logging.info(f"AFC Data Extracted: {afc_data}")

        # Control for the update of the UI
        self.update_info = False

        self.afc_units = []
        self.afc_unit_names = []
        self.afc_lane_data = []
        self.afc_lanes = []
        self.afc_system = None
        self.current_load = None
        self.spoolman = None
        self.labels = {}
        self.buttons = {}
        self.action_buttons = {}
        self.move_lane = None
        self.distance = 5
        self.last_drop_time = datetime.now()
        self.hub_states = {}  # Track the current state of each hub
        self.selected_lane = None
        self.selected_color = "#000000"
        self.selected_type = None
        self.selected_weight = 0

        self.data = self.apiClient.post_request("printer/objects/list", json={})
        sensor_data = self.data.get('result', {}).get('objects', {})
        self.filament_sensors = [
            name for name in sensor_data
            if name.startswith("filament_switch_sensor")
        ]

        for unit_name, unit_data in afc_data.items():
            if unit_name == "system":
                # Process system data
                self.afc_system = self.process_system_data(unit_data)
                self.current_load = self.afc_system.current_load
                self.spoolman = self.afc_system.spoolman
                logging.info(f"spoolman: {self.spoolman}")
                continue  # Skip the system entry

            if not isinstance(unit_data, dict):
                logging.warning(f"Unexpected unit_data format for {unit_name}: {unit_data}")
                continue

            logging.info(f"Processing unit: {unit_name}")
            unit_lanes = []

            system_type = unit_data.get("system", {}).get("type", "Unknown")

            for lane_name, lane_data in unit_data.items():
                logging.info(f"Checking lane: {lane_name}")

                if not isinstance(lane_data, dict) or not lane_name.startswith("lane"):
                    logging.info(f"Skipping non-lane entry: {lane_name}")
                    continue

                lane_obj = AFClane(
                    name=lane_name,
                    unit=unit_name,
                    lane_data=lane_data
                )
                lane_obj.status = self.get_lane_status(lane_obj)
                logging.info(f"lane status {lane_obj.status}")
 
                unit_lanes.append(lane_obj)
                self.afc_lane_data.append(lane_obj)
                self.afc_lanes.append(lane_obj.name)

            unit_obj = AFCunit(name=unit_name, lanes=unit_lanes, system_type=system_type)
            self.afc_units.append(unit_obj)
            self.afc_unit_names.append(unit_obj.name)

        logging.info(f"Final AFC Lanes: {self.afc_lane_data}")
        logging.info(f"Unit names: {self.afc_unit_names}")
        logging.info(f"lane names: {self.afc_lanes}")

        self.init_layout()
        self.sensor_layout()
        self.create_spool_layout()
    
    def get_afc_lanes(self):
        """
        Return the list of AFC lanes.
        """
        return self.afc_lanes
        
    def process_update(self, action, data):
        """
        Process the update from the printer.
        """
        if not self.update_info:
            return

        api_data = self.apiClient.post_request("printer/afc/status", json={})
        afc_data = api_data.get('result', {}).get('status:', {}).get('AFC', {})
        if afc_data:
            self.update_ui(afc_data)

        if action == "notify_gcode_response":
            if "action:cancel" in data or "action:paused" in data:
                self.enable_buttons(True)
            elif self._printer.state == "printing":
                self.enable_buttons(False)
            elif "action:resumed" in data:
                self.enable_buttons(False)
            return
        if action != "notify_status_update":
            return

    def enable_buttons(self, enable):
        for button in self.action_buttons:
            self.action_buttons[button].set_sensitive(enable)

    def activate(self):
        self.update_info = True
        # self.screen_stack.set_visible_child_name("main_grid")
        # self.stack.set_visible_child_name("control_grid")
        self.enable_buttons(self._printer.state in ("ready", "paused"))

    def deactivate(self):
        self.update_info = False
        self.enable_buttons(False)
        self.screen_stack.set_visible_child_name("main_grid")
        self.stack.set_visible_child_name("control_grid")

    def process_system_data(self, system_data):
        extruders = {name: Extruder(**data) for name, data in system_data.get("extruders", {}).items()}
        hubs = {name: Hub(**data) for name, data in system_data.get("hubs", {}).items()}
        buffers = {name: Buffer(**data) for name, data in system_data.get("buffers", {}).items()}
        
        return AFCsystem(
            current_load=system_data.get("current_load"),
            num_units=system_data.get("num_units"),
            num_lanes=system_data.get("num_lanes"),
            num_extruders=system_data.get("num_extruders"),
            spoolman=system_data.get("spoolman"),
            current_toolchange=system_data.get("current_toolchange"),
            number_of_toolchanges=system_data.get("number_of_toolchanges"),
            extruders=extruders,
            hubs=hubs,
            buffers=buffers
        )

    def reset_ui(self):
        # Create the main layout grid
        self.screen_stack = Gtk.Stack()
        self.screen_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.screen_stack.set_transition_duration(300)

        self.grid = Gtk.Grid(column_homogeneous=True) #AutoGrid()  
        self.grid.set_vexpand(True)

        self.sensor_grid = Gtk.Grid(column_homogeneous=True)
        self.grid.set_vexpand(True)

        self.selector_grid = Gtk.Grid(column_homogeneous=True)
        self.selector_grid.set_vexpand(True)

        self.screen_stack.add_named(self.grid, "main_grid")
        self.screen_stack.add_named(self.sensor_grid, "sensor_grid")
        self.screen_stack.add_named(self.selector_grid, "selector_grid")
        
        self.content.add(self.screen_stack)

    def remove_all_classes(self, widget):
        """
        Remove all CSS classes from the widget's style context.
        """
        style_context = widget.get_style_context()
        for css_class in style_context.list_classes():
            style_context.remove_class(css_class)

    def init_layout(self):
        # Extruder Tools
        extruder_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        extruder_tools = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, homogeneous=False, spacing=5)
        extruder_tools.set_size_request(-1, 20)  # Fixed height
        extruder_tools.set_hexpand(True)
        extruder_tools.set_vexpand(False)

        current_lane = next((lane for lane in self.afc_lane_data if lane.name == self.current_load), None)

        # Create labels
        extruder_label = Gtk.Label(label=f"Extruder: {current_lane.extruder}" if current_lane else "Extruder: N/A")
        buffer_label = Gtk.Label(label=f"Buffer: {current_lane.buffer} - {current_lane.buffer_status}" if current_lane else "Buffer: N/A")
        loaded_label = Gtk.Label(label=f"Loaded: {self.current_load}" if self.current_load else "Loaded: N/A")

        # Add styling and alignment
        for label, key in zip(
            [extruder_label, buffer_label, loaded_label],
            ["extruder_label", "buffer_label", "loaded_label"]
        ):
            label.get_style_context().add_class(key)
            label.set_hexpand(True)
            label.set_halign(Gtk.Align.FILL)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            self.labels[key] = label
            extruder_tools.pack_start(label, True, True, 0)

        extruder_container.pack_start(extruder_tools, True, True, 0)
        self.grid.attach(extruder_container, 0, 0, 4, 1)
        extruder_tools.get_style_context().add_class("button_active")

        # Units and Lanes
        self.create_unit_lane_layout()
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(300)

        self.control_grid = self.create_controls()
        self.stack.add_named(self.control_grid, "control_grid") 

        self.more_controls = self.create_more_controls()
        self.stack.add_named(self.more_controls, "more_controls")

        self.lane_move_grid = self.create_lane_move_grid()
        self.stack.add_named(self.lane_move_grid, "lane_move_grid")

        self.grid.attach(self.stack, 0, 2, 4, 1)

    def create_unit_lane_layout(self):
        unit_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, homogeneous=False, spacing=5)
        unit_box.set_hexpand(False)
        unit_box.set_vexpand(False)  # Ensure unit_box does not expand vertically
        unit_box.set_valign(Gtk.Align.START)
        
        for unit in self.afc_units:
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)

            # Get the icon filename from the mapping
            icon_filename = SYSTEM_TYPE_ICONS.get(unit.system_type)
            if icon_filename:
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                        filename=os.path.join(self.image_path, icon_filename),
                        width=45,
                        height=45,
                        preserve_aspect_ratio=True
                    )
                    unit_icon = Gtk.Image.new_from_pixbuf(pixbuf)
                    box.pack_start(unit_icon, False, False, 0)
                except Exception as e:
                    logging.info(f"Could not load image for {unit.system_type}: {e}")
            else:
                logging.warning(f"No icon defined for system type: {unit.system_type}")

            # Create a Gtk.Image from the scaled pixbuf
            unit_name_label = unit.name.replace("_", " ")
            unit_label = Gtk.Label(label=unit_name_label)
            box.pack_start(unit_label, False, False, 0)
            unit_hub = Gtk.Label(label=" | Hub")
            self.labels[f"{unit.name}_hub"] = unit_hub
            box.pack_start(unit_hub, False, False, 0)

            # Get the initial state of the hub
            hub_state = self.afc_system.hubs.get(unit.name).state if self.afc_system and unit.name in self.afc_system.hubs else False
            logging.info(f"Hub state for {unit.name}: {hub_state}")

            # Create the status dot with the initial state
            status_dot = Gtk.EventBox()
            dot = Gtk.Label(label=" ")
            dot.set_size_request(20, 20)
            dot.set_valign(Gtk.Align.CENTER)
            dot.set_halign(Gtk.Align.START)
            dot.get_style_context().add_class("status-active" if hub_state else "status-empty")
            status_dot.add(dot)

            # Store the status dot reference for updates
            self.labels[f"{unit.name}_status_dot"] = dot

            box.pack_start(status_dot, False, False, 0)

            unit_expander = Gtk.Expander()
            unit_expander.set_label_widget(box)

            unit_expander.set_expanded(True)  # Open the first expander by default
            lane_grid = AutoGrid()
            lane_grid.set_vexpand(False)  # Ensure lane_grid does not expand vertically
            lane_grid.set_hexpand(False)

            # Dynamically calculate the number of lanes per row based on screen width
            logging.info(f"Screen width: {self._screen.width}")
            lane_box_width = 150 + 10  # Lane frame width + margins (adjust as needed)
            lanes_per_row = max(1, (self._screen.width - 150) // lane_box_width)  # At least one lane per row
            logging.info(f"screen width {self._screen.width}")

            for j, lane in enumerate(unit.lanes):
                # Calculate row and column positions dynamically
                row = j // lanes_per_row  # Each row contains up to 'lanes_per_row' lanes
                col = j % lanes_per_row   # Column index within the row

                lane_frame = Gtk.Frame()
                lane_frame.set_size_request(150, 200)  # Set a fixed width for lane frames
                lane_frame.set_vexpand(False)  # Ensure lane_frame does not expand vertically
                lane_frame.set_hexpand(False)
                lane_frame.set_valign(Gtk.Align.START)

                lane_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
                lane_box.get_style_context().add_class("button_active")

                lane_info_box = self.create_lane_info_box(lane)
                lane_info_box.set_margin_end(5)
                lane_info_box.set_margin_start(5)
                lane_info_box.set_margin_top(5)
                lane_info_box.set_margin_bottom(5)
                lane_info_box.set_valign(Gtk.Align.START)
                lane_box.pack_start(lane_info_box, True, True, 0)

                lane_frame.add(lane_box)
                lane_frame.set_margin_start(5)
                lane_frame.set_margin_end(5)
                lane_frame.set_margin_top(2)
                lane_frame.set_margin_bottom(2)

                # Attach the lane frame to the grid at the calculated position
                lane_grid.attach(lane_frame, col, row, 1, 1)

                # if lane.name == self.current_load:
                #     lane_frame.get_style_context().add_class("highlighted-lane")

                # Store the lane_box for updating purposes
                self.lane_widgets[lane.name] = lane_box

            unit_expander.add(lane_grid)
            unit_box.pack_start(unit_expander, False, False, 0)

        scroll = self._gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(unit_box)

        self.grid.attach(scroll, 0, 1, 4, 1)  # Attach unit box to grid
        self.grid.show_all()

        self.set_uniform_frame_height()

    def create_lane_info_box(self, lane):
        lane_info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        lane_button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        lane_button_box.set_vexpand(False)
        lane_button_box.set_size_request(-1, 30)

        # Create a lane name label
        lane_name = Gtk.Label(label=f"{lane.name}")
        lane_name.set_halign(Gtk.Align.FILL)
        self.labels[f"{lane.name}"] = lane_name
        self.remove_all_classes(lane_name)

        # Set the color of the lane name
        status = self.get_lane_status(lane)
        status_color = self.set_lane_status(lane, status)
        for style in status_color:
            lane_name.get_style_context().add_class(style)

        lane_button_box.pack_start(lane_name, True, True, 0)

        # Replace dropdown with MenuButton for lane mapping
        lane_map_menu_button = self.create_lane_map_menu_button(lane)
        lane_map_menu_button.set_halign(Gtk.Align.FILL)
        lane_map_menu_button.set_size_request(-1, 25)  # Set a fixed height for the menu button
        lane_map_menu_button.get_style_context().add_class("color2")
        lane_button_box.pack_start(lane_map_menu_button, True, True, 0)

        lane_info_box.pack_start(lane_button_box, False, False, 0)

        lane_info_grid = self.create_lane_info_grid(lane, lane_name, status)
        lane_info_box.pack_start(lane_info_grid, False, False, 0)
        
        return lane_info_box

    def create_lane_info_grid(self, lane, lane_name, status):
        lane_info_grid = AutoGrid()
        lane_info_grid.set_row_homogeneous(False)
        lane_info_grid.set_column_homogeneous(True)
        lane_info_grid.set_row_spacing(0)
        lane_info_grid.set_column_spacing(0)
        lane_info_grid.set_hexpand(False)
        lane_info_grid.set_vexpand(False)

        if status == "prep not load":
            warning_label = Gtk.Label(label="Filament not detected at the extruder", wrap=True)
            warning_label.set_justify(Gtk.Justification.CENTER)
            warning_label.set_valign(Gtk.Align.START)
            lane_info_grid.attach(warning_label, 0, 0, 3, 3)
            lane_name.get_style_context().add_class("status-warning")
        elif status == "load not prep":
            warning_label = Gtk.Label(label="Lane loaded not prepped", wrap=True)
            warning_label.set_justify(Gtk.Justification.CENTER)
            warning_label.set_valign(Gtk.Align.START)
            lane_info_grid.attach(warning_label, 0, 0, 3, 3)
            lane_name.get_style_context().add_class("status-warning")
        elif status == "unloaded":
            empty_label = Gtk.Label(label="Lane Empty", wrap=True)
            empty_label.set_justify(Gtk.Justification.CENTER)
            empty_label.set_hexpand(True)
            empty_label.set_valign(Gtk.Align.CENTER)
            empty_label.set_halign(Gtk.Align.FILL)
            empty_label.set_margin_top(45)
            empty_label.set_margin_bottom(45)
            lane_info_grid.attach(empty_label, 2, 2, 3, 3)
            lane_name.get_style_context().add_class("status-lane-empty")
        else:
            # over_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            overlay = Gtk.Overlay()

            # Icon button is in the background
            icon = Gtk.Image.new_from_pixbuf(lane.icon(width=40, height=70))
            icon_button = Gtk.Button()
            icon_button.set_image(icon)
            icon_button.set_always_show_image(True)
            icon_button.set_halign(Gtk.Align.START)
            icon_button.connect("clicked", self.show_selector_grid, lane)
            icon_button.get_style_context().add_class("no-background")
            overlay.add(icon_button)

            # Runout button in front
            runout_menu_button = self.create_lane_inf_menu_button(lane)
            runout_menu_button.set_halign(Gtk.Align.END)
            runout_menu_button.set_hexpand(True)
            runout_menu_button.get_style_context().add_class("color3")
            overlay.add_overlay(runout_menu_button)
            # over_box.pack_start(overlay, True, True, 0)

            lane_info_grid.attach(overlay, 0, 0, 2, 1)

            # Material button in b2
            material_button = Gtk.Label(label=f"{lane.material}")
            material_button.set_halign(Gtk.Align.FILL)
            material_button.set_hexpand(True)
            # material_button.set_margin_start(25)
            lane_info_grid.attach(material_button, 0, 1, 1, 1)

            # Weight button in b3
            weight_button = Gtk.Label(label=f"{lane.weight}g")
            weight_button.set_halign(Gtk.Align.FILL)
            # weight_button.set_margin_start(40)
            lane_info_grid.attach(weight_button, 1, 1, 1, 1)

            lane_action_box = self.create_lane_action_box(lane, status)
            lane_info_grid.attach(lane_action_box, 0, 2, 2, 2)

            self.buttons[f"{lane.name}_icon_button"] = icon_button
            self.buttons[f"{lane.name}_runout_button"] = runout_menu_button
            self.labels[f"{lane.name}_material_label"] = material_button
            self.labels[f"{lane.name}_weight_label"] = weight_button

        self.labels[f"{lane.name}_lane_info_grid"] = lane_info_grid

        return lane_info_grid

    def create_lane_action_box(self, lane, status):
        action_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, homogeneous=True, spacing=1)
        action_box.set_hexpand(True)
        action_box.set_vexpand(True)  # Ensure unit_box does not expand vertically

        load_button = Gtk.Button(label="LOAD")
        load_button.set_halign(Gtk.Align.FILL)
        load_button.set_hexpand(True)
        load_button.connect("clicked", self.on_load_lane_clicked, lane)
        load_button.get_style_context().add_class("color4")


        eject_button = Gtk.Button(label="EJECT")
        eject_button.set_halign(Gtk.Align.FILL)
        eject_button.set_hexpand(True)
        eject_button.connect("clicked", self.on_eject_lane_clicked, lane)
        eject_button.get_style_context().add_class("color4")

        unload_button = Gtk.Button(label="UNLOAD")
        unload_button.set_halign(Gtk.Align.FILL)
        unload_button.set_hexpand(True)
        unload_button.connect("clicked", self.on_unload_lane_clicked, lane)
        unload_button.get_style_context().add_class("color4")

        if status == "loaded":
            action_box.pack_start(load_button, True, True, 0)
            action_box.pack_start(eject_button, True, True, 0)
        elif status == "tooled":
            action_box.pack_start(unload_button, True, True, 0)
            action_box.pack_start(eject_button, True, True, 0)

        self.action_buttons[f"{lane.name}_load_button"] = load_button
        self.action_buttons[f"{lane.name}_eject_button"] = eject_button
        self.action_buttons[f"{lane.name}_unload_button"] = unload_button

        return action_box

    def calculate_max_frame_height(self):
        max_height = 0
        for lane_name, lane_box in self.lane_widgets.items():
            lane_frame = lane_box.get_parent()  # Get the parent frame of the lane_box
            if lane_frame:
                _, natural_height = lane_frame.get_preferred_height()
                max_height = max(max_height, natural_height)
        return max_height

    def set_uniform_frame_height(self):
        max_height = self.calculate_max_frame_height()
        for lane_name, lane_box in self.lane_widgets.items():
            lane_frame = lane_box.get_parent()  # Get the parent frame of the lane_box
            if lane_frame:
                lane_frame.set_size_request(-1, max_height)  # Apply the maximum height
                lane_frame.queue_resize()  # Trigger a redraw

    ################
    # Controls     #
    ################

    def create_controls(self):
        controls_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        controls_box.set_hexpand(False)
        controls_box.set_vexpand(False)

        button_grid = AutoGrid()
        button_grid.set_column_homogeneous(False)
        button_grid.set_halign(Gtk.Align.START)

        temp_button = self._gtk.Button("heat-up", _("Temp"), "color2")
        temp_button.set_halign(Gtk.Align.START)
        self.buttons['temperature'] = temp_button
        self.buttons['temperature'].connect("clicked", self.menu_item_clicked, {"panel": "temperature"})
        button_grid.attach(self.buttons['temperature'], 1, 0, 1, 1)

        home_button = self._gtk.Button("move", _("Move"), "color1")
        home_button.set_halign(Gtk.Align.START)
        self.buttons['move'] = home_button
        self.buttons['move'].connect("clicked", self.menu_item_clicked, {"panel": "move"})
        button_grid.attach(self.buttons['move'], 0, 0, 1, 1)

        extrude_button = self._gtk.Button("extrude", _("Extrude"), "color3")
        extrude_button.set_halign(Gtk.Align.START)
        self.buttons['extrude'] = extrude_button
        self.buttons['extrude'].connect("clicked", self.menu_item_clicked, {"panel": "extrude"})
        button_grid.attach(self.buttons['extrude'], 2, 0, 1, 1)

        # Add the filament sensors button
        sensors_button = self._gtk.Button("info", _("Sensors"), "color4")
        # sensors_button.connect("clicked", self.menu_item_clicked, {"panel": "filament_sensors"})
        sensors_button.connect("clicked", self.show_sensor_grid)
        button_grid.attach(sensors_button, 3, 0, 1, 1)

        move_button = self._gtk.Button("filament", _("Lane Move"), "color1")
        move_button.connect("clicked", self.show_lane_move_grid)
        self.action_buttons['lane_move'] = move_button
        button_grid.attach(move_button, 4, 0, 1, 1)

        # Add a button to navigate to more controls
        more_controls_button = self._gtk.Button("increase", _("More"), "color2")
        more_controls_button.connect("clicked", self.show_more_controls)
        button_grid.attach(more_controls_button, 5, 0, 1, 1)

        controls_box.pack_start(button_grid, False, False, 0)

        toolchange_label = Gtk.Label(label="Toolchanges:")
        toolchange_label.set_halign(Gtk.Align.END)
        controls_box.pack_start(toolchange_label, False, False, 0)

        toolchange_combined_label = Gtk.Label(label="0/0")
        toolchange_combined_label.get_style_context().add_class("toolchange_combined_label")
        self.labels["toolchange_combined_label"] = toolchange_combined_label  # Store reference for updates
        controls_box.pack_start(toolchange_combined_label, False, False, 10)

        alignment = Gtk.Alignment.new(0.5, 1.0, 1.0, 0.0)
        alignment.add(controls_box)

        return alignment

    def show_lane_move_grid(self, button):
        """
        Switch to the lane move grid.
        """
        self.stack.set_visible_child_name("lane_move_grid")

    def show_control_grid(self, button):
        """
        Switch back to the control grid.
        """
        self.stack.set_visible_child_name("control_grid")

    def show_more_controls(self, button):
        """
        Switch to the 'More Controls' section.
        """
        self.stack.set_visible_child_name("more_controls")

    def show_main_grid(self, button):
        """
        Switch to the lane move grid.
        """
        self.screen_stack.set_visible_child_name("main_grid")

    def show_sensor_grid(self, button):
        """
        Switch to the lane move grid.
        """
        self.screen_stack.set_visible_child_name("sensor_grid")

    def show_selector_grid(self, button, lane):
        """
        Switch to the selector grid and populate input fields with the lane's information.
        """
        if self.spoolman is not None:
            self._screen.show_popup_message(_("Spoolman not currently supported, manual spool set available"))

        logging.info(f"Switching to selector grid for lane: {lane.name}")
        self.selected_lane = lane  # Store the selected lane

        self.labels["title_label"].set_label(f"Change Spool {lane.name}")

        # Populate input fields with lane information
        if lane.color:
            rgba = Gdk.RGBA()
            rgba.parse(lane.color)
            r = int(rgba.red * 255)
            g = int(rgba.green * 255)
            b = int(rgba.blue * 255)
            self.r_input.set_text(str(r))
            self.g_input.set_text(str(g))
            self.b_input.set_text(str(b))
            self.hex_input.set_text(f"#{r:02X}{g:02X}{b:02X}")
            self.color_button.set_rgba(rgba)  # Update the color button
        else:
            # Default color if no color is set
            self.r_input.set_text("255")
            self.g_input.set_text("0")
            self.b_input.set_text("0")
            self.hex_input.set_text("#FF0000")
            self.color_button.set_rgba(Gdk.RGBA(1, 0, 0, 1))  # Default to red

        if lane.material:
            self.labels["type_input"].set_text(lane.material)
        else:
            self.labels["type_input"].set_text("")

        if lane.weight:
            self.labels["weight_input"].set_text(str(lane.weight))
        else:
            self.labels["weight_input"].set_text("")

        self.screen_stack.set_visible_child_name("selector_grid")
        self._screen.remove_keyboard()

    def create_lane_move_grid(self):
        """
        Create the lane move grid with dropdown, distance grid, move button, and exit button.
        """
        vbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        vbox.set_hexpand(False)
        vbox.set_vexpand(False)
        vbox.set_margin_top(0)
        vbox.set_margin_bottom(5)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)

        exit_button = self._gtk.Button("back", _("back"), "color2")
        exit_button.connect("clicked", self.show_control_grid)
        vbox.pack_start(exit_button, False, False, 5)

        # Create the dropdown for lane selection
        lane_dropdown = self.create_lane_dropdown()
        lane_dropdown.set_valign(Gtk.Align.CENTER)
        vbox.pack_start(lane_dropdown, False, False, 0)

        neg_move_button = self._gtk.Button("decrease", _("Move"), "color1")
        neg_move_button.connect("clicked", self.on_neg_move_button_clicked)
        vbox.pack_start(neg_move_button, False, False, 5)

        # Create the distance grid
        distbox = self.create_distance_grid()
        vbox.pack_start(distbox, True, True, 0)

        # Add the move button
        move_button = self._gtk.Button("increase", _("Move"), "color3")
        move_button.connect("clicked", self.on_move_button_clicked)
        vbox.pack_start(move_button, False, False, 5)

        return vbox

    def update_toolchange_combined_label(self):
        """
        Update the combined toolchange/toolchanges label in the UI.
        """
        toolchange_combined_label = self.labels.get("toolchange_combined_label")
        if toolchange_combined_label:
            toolchange_combined_label.set_label(
                f"{self.afc_system.current_toolchange}/{self.afc_system.number_of_toolchanges}")

    #################
    # More Controls #
    #################

    def create_more_controls(self):
        """
        Create the 'More Controls' section with additional controls like the AFC LED switch.
        """
        more_controls_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        more_controls_box.set_hexpand(True)
        more_controls_box.set_vexpand(False)

        # Add a back button to return to the main controls
        exit_button = self._gtk.Button("back", _("back"), "color2")
        exit_button.set_halign(Gtk.Align.START)
        exit_button.connect("clicked", self.show_control_grid)
        more_controls_box.pack_start(exit_button, False, False, 5)

        calibration_button = self._gtk.Button("fine-tune", _("Calibration"), "color1")
        calibration_button.set_halign(Gtk.Align.START)
        calibration_button.connect("clicked", self.on_calibration_clicked)
        self.action_buttons['calibration'] = calibration_button
        more_controls_box.pack_start(calibration_button, False, False, 5)

        macro_button = self._gtk.Button("custom-script", _("Macros"), "color3")
        macro_button.set_halign(Gtk.Align.START)
        macro_button.connect("clicked", self.afc_macros)
        more_controls_box.pack_start(macro_button, False, False, 5)

        # Create a vertical box to hold the label and the switch
        afc_led_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        afc_led_box.set_halign(Gtk.Align.FILL)
        afc_led_box.set_hexpand(False)
        afc_led_box.set_vexpand(False)

        # Create a label for the switch
        afc_led_label = Gtk.Label(label="AFC LED")
        afc_led_label.set_halign(Gtk.Align.FILL)  # Center the label horizontally
        afc_led_label.set_valign(Gtk.Align.END)  # Center the label vertically
        afc_led_box.pack_start(afc_led_label, False, False, 0)

        # Create the AFC LED switch
        afc_led_switch = Gtk.Switch()
        afc_led_switch.get_style_context().add_class("filament_sensor_detected")
        afc_led_switch.set_vexpand(False)  # Prevent vertical expansion
        afc_led_switch.set_valign(Gtk.Align.END)  # Center the switch vertically
        afc_led_switch.set_size_request(50, 25)  # Set a fixed size for the switch
        afc_led_switch.set_active(True)  # Default state is "on"
        afc_led_switch.connect("state-set", self.on_afc_led_switched)
        afc_led_box.pack_start(afc_led_switch, False, False, 5)

        # Add the AFC LED box to the more controls box
        more_controls_box.pack_start(afc_led_box, False, False, 5)

        return more_controls_box

    def on_calibration_clicked(self, switch):
        self._screen._send_action(switch, "printer.gcode.script", {"script": "AFC_CALIBRATION"})
        logging.info("AFC Calibration button clicked")

    def afc_macros(self, widget):
        name = "afc_macros"
        disname = self._screen._config.get_menu_name("afc", name)
        menuitems = self._screen._config.get_menu_items("afc", name)
        self._screen.show_panel("menu", disname, panel_name=name, items=menuitems)

    def on_afc_led_switched(self, switch, state):
        """
        Handle the AFC LED switch state and update its style.
        """
        # Remove all existing CSS classes related to the switch state
        style_context = switch.get_style_context()
        style_context.remove_class("filament_sensor_detected")
        style_context.remove_class("filament_sensor_empty")

        if state:  # Switch is turned on
            logging.info("AFC LED turned ON")
            self._screen._send_action(switch, "printer.gcode.script", {"script": "TURN_ON_AFC_LED"})
            style_context.add_class("filament_sensor_detected")  # Add the "on" style
        else:  # Switch is turned off
            logging.info("AFC LED turned OFF")
            self._screen._send_action(switch, "printer.gcode.script", {"script": "TURN_OFF_AFC_LED"})
            style_context.add_class("filament_sensor_empty")  # Add the "off" style

        return True  # Allow the state change

    def create_lane_map_menu_button(self, lane):
        """
        Creates a MenuButton for lane mapping, displaying T values instead of lane names.

        :param lane: The current lane object.
        :return: A Gtk.MenuButton widget.
        """
        options = {
            f"T{lane_num - 1}": lane_name
            for lane_num, lane_name in enumerate(self.afc_lanes, start=1)
        }
        # options = {"T1": "T1", "T2": "T2", "T3": "T3", "T4": "T4", "T5": "T5", "T6": "T6",
        # "T11": "T11", "T21": "T21", "T31": "T31", "T41": "T41", "T51": "T51", "T61": "T61",
        # "T12": "T12", "T22": "T22", "T32": "T32", "T42": "T42", "T52": "T52", "T62": "T62"}

        logging.info(f"Options passed to menu button: {options}")
        logging.info(f"Initial selection (lane.map): {lane.map}")

        initial_selection = None
        for t_value, lane_name in options.items():
            if t_value == lane.map:
                initial_selection = t_value
                break

        if initial_selection is None:
            logging.warning(f"Initial map value '{lane.map}' not found in options. Defaulting to the first.")
            initial_selection = list(options.keys())[0]

        # Create the menu button
        label = Gtk.Label(label=lane.map)
        menu_button = Gtk.MenuButton()
        menu_button.add(label)
        menu_button.set_halign(Gtk.Align.END)
        menu_button.set_vexpand(False)

        # Create the popover
        popover = Gtk.Popover()

        # Add a scrolled window to the popover
        scrolled_window = self._gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_min_content_height(450)  # adjust to your needs
        scrolled_window.set_max_content_height(600)  # limit how tall the popover grows
        scrolled_window.set_min_content_width(600)  # adjust to your needs

        # Container for the scrollable content
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin=5)
        scrolled_window.add(box)

        # Add buttons to the box
        for t_value in options:
            item = Gtk.ModelButton(label=t_value)
            item.get_style_context().add_class("scroll_button")
            item.set_halign(Gtk.Align.START)
            item.get_style_context().add_class("large-button")

            def on_select(_, value=t_value):
                logging.info(f"MenuButton selection changed: {value}")
                self.on_lane_map_changed(menu_button, value, lane, label)

            item.connect("clicked", on_select)
            box.pack_start(item, True, True, 2)

        box.show_all()
        scrolled_window.show_all()
        popover.add(scrolled_window)
        menu_button.set_popover(popover)

        self.labels[f"{lane.name}_map_menu_button"] = menu_button
        return menu_button


    def create_lane_inf_menu_button(self, lane):
        """
        Creates a MenuButton for lane INF selection, displaying lane names.

        :param lane: The current lane object.
        :return: A Gtk.MenuButton widget.
        """
        # Use lane names as options, excluding the current lane's name and adding "None"
        options = ["NONE"] + [lane_name for lane_name in self.afc_lanes if lane_name != lane.name]

        logging.info(f"Options passed to menu button: {options}")
        logging.info(f"Initial selection (lane.inf): {lane.runout_lane}")

        # Validate current lane.inf
        initial_selection = lane.runout_lane if lane.runout_lane in options else "NONE"
        if lane.runout_lane not in options:
            logging.warning(f"Initial INF value '{lane.runout_lane}' not found in options. Defaulting to '{initial_selection}'")

        # Create the menu button
        label = Gtk.Label(label=f"{initial_selection} ∞")
        menu_button = Gtk.MenuButton()
        menu_button.add(label)
        menu_button.set_halign(Gtk.Align.END)
        menu_button.set_vexpand(False)

        # Create the popover menu
        popover = Gtk.Popover()

        # Add a scrolled window to the popover
        scrolled_window = self._gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_min_content_height(450)  # adjust to your needs
        scrolled_window.set_max_content_height(600)  # limit how tall the popover grows
        scrolled_window.set_min_content_width(600)  # adjust to your needs

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=10)
        scrolled_window.add(box)

        # Create buttons for each option
        for lane_name in options:
            item = Gtk.ModelButton(label=lane_name)
            item.get_style_context().add_class("scroll_button")
            item.set_name("lane-inf-item")
            item.set_halign(Gtk.Align.FILL)
            item.get_style_context().add_class("large-button")

            def on_select(_, value=lane_name):
                logging.info(f"MenuButton selection changed: {value} ∞")
                self.on_lane_inf_changed(menu_button, value, lane, label)

            item.connect("clicked", on_select)
            box.pack_start(item, True, True, 0)

        box.show_all()
        scrolled_window.show_all()
        popover.add(scrolled_window)
        menu_button.set_popover(popover)

        # Store reference
        self.labels[f"{lane.name}_inf_menu_button"] = menu_button
        return menu_button

    ##################
    #    Updating    #
    ##################

    def update_ui(self, afc_data):
        try:
            if not afc_data or not isinstance(afc_data, dict):
                logging.error("Invalid AFC data received")
                return

            # logging.info(f"Full AFC data received: {afc_data}")  # Log the full data
            # Update AFCsystem attributes
            system_data = afc_data.get("system", {})
            if system_data:
                self.update_afc_system(system_data)

            # Update hub statuses
            hubs_data = system_data.get("hubs", {})  # Corrected path to hubs data
            if not hubs_data:
                logging.warning("No hub data found in the AFC system data")
            else:
                for hub_name, hub_data in hubs_data.items():
                    hub_state = hub_data.get("state", False)  # Default to False if state is not provided
                    self.update_hub_status(hub_name, hub_state)

            for unit in self.afc_units:
                for lane in unit.lanes:
                    lane_data = afc_data.get(unit.name, {}).get(lane.name)
                    if not lane_data:
                        logging.warning(f"No data found for lane: {lane.name}")
                        continue

                    lane_status = self.get_lane_status_from_data(lane_data)
                    lane_name = self.labels.get(f"{lane.name}")

                    if lane.status != lane_status:
                        self.handle_lane_status_update(lane, lane_status)

                    new_map = lane_data.get("map", lane.map)
                    if lane.map != new_map:
                        logging.info(f"Updating mapping for {lane.name}: {lane.map} → {new_map}")
                        lane.map = new_map
                        self.update_lane_map(lane)

                    if lane.runout_lane != lane_data.get("runout_lane", lane.runout_lane):
                        lane.runout_lane = lane_data.get("runout_lane", lane.runout_lane)
                        self.update_lane_runout(lane)

                    if lane.material != lane_data.get("material", lane.material):
                        lane.material = lane_data.get("material", lane.material)
                        self.update_lane_material(lane)

                    new_weight = round(float(lane_data.get("weight", lane.weight) or 0))
                    if lane.weight != new_weight:
                        lane.weight = new_weight
                        self.update_lane_weight(lane)

                    if lane.color != lane_data.get("color", lane.color):
                        lane.color = lane_data.get("color", lane.color)
                        self.update_lane_color(lane)

                    if lane.load != bool(lane_data.get("load", lane.load)):
                        lane.load = bool(lane_data.get("load", lane.load))
                        self.update_lane_load(lane)

        except Exception as e:
            logging.error(f"Failed to update UI: {e}")

    def update_hub_status(self, hub_name, hub_state):
        """
        Update the status dot style based on the hub's state, only if the state changes.

        :param hub_name: The name of the hub.
        :param hub_state: The current state of the hub (True for active, False for empty).
        """
        # Check if the state has changed
        if self.hub_states.get(hub_name) == hub_state:
            # logging.info(f"No change in state for hub: {hub_name} (state: {hub_state})")
            return  # No update needed

        # Update the stored state
        self.hub_states[hub_name] = hub_state

        # Get the status dot widget
        status_dot = self.labels.get(f"{hub_name}_status_dot")
        if not status_dot:
            # logging.warning(f"Status dot not found for hub: {hub_name}")
            return

        # Get the style context of the status dot
        style_context = status_dot.get_style_context()

        # Remove all existing status-related classes
        style_context.remove_class("status-active")
        style_context.remove_class("status-empty")

        # Add the appropriate class based on the hub state
        if hub_state:
            style_context.add_class("status-active")  # Green for active
            # logging.info(f"Hub {hub_name} state updated to ACTIVE")
        else:
            style_context.add_class("status-empty")  # Red for empty
            # logging.info(f"Hub {hub_name} state updated to EMPTY")

    def update_afc_system(self, system_data):
        """
        Update the AFCsystem attributes and check for changes in current_load,
        current_toolchange, and number_of_toolchanges.
        """
        if not self.afc_system:
            logging.warning("AFCsystem is not initialized.")
            return

        # Check and update current_load
        new_current_load = system_data.get("current_load", self.afc_system.current_load)
        if self.afc_system.current_load != new_current_load:
            logging.info(f"Current load changed: {self.afc_system.current_load} → {new_current_load}")
            self.afc_system.current_load = new_current_load
            self.update_system_container()

        # Check and update current_toolchange
        new_toolchange = system_data.get("current_toolchange", self.afc_system.current_toolchange)
        new_toolchange_count = system_data.get("number_of_toolchanges", self.afc_system.number_of_toolchanges)

        if (self.afc_system.current_toolchange != new_toolchange or
                self.afc_system.number_of_toolchanges != new_toolchange_count):
            logging.info(f"Toolchange updated: {self.afc_system.current_toolchange}/{self.afc_system.number_of_toolchanges} → {new_toolchange}/{new_toolchange_count}")
            self.afc_system.current_toolchange = new_toolchange
            self.afc_system.number_of_toolchanges = new_toolchange_count
            self.update_toolchange_combined_label()

    def handle_lane_status_update(self, lane, lane_status):
        logging.info(f"Handling lane status update for {lane.name}: {lane.status} → {lane_status}")

        UNREADY_STATUSES = {"unloaded", "prep not load", "load not prep"}
        READY_STATUSES = {"loaded", "tooled"}

        def status_category(status):
            if status in UNREADY_STATUSES:
                return "unready"
            elif status in READY_STATUSES:
                return "ready"
            return "other"

        old_status = lane.status  # Save the previous status
        old_category = status_category(old_status)
        new_category = status_category(lane_status)

        # Update the lane's status before rebuilding the grid
        lane.status = lane_status

        # Determine if the UI needs to be refreshed
        should_update = (
            old_category != new_category  # Changed category (e.g., ready ↔ unready)
            or (old_status != lane_status and old_category == "unready")  # Changed within unready
        )

        if old_status != lane_status:
            logging.info(f"Updating UI grid for {lane.name} due to status change: {lane_status}")
            self.replace_lane_info_grid(lane, self.labels.get(f"{lane.name}"), lane_status)

        # Update the lane's status in the UI
        self.update_lane_status(lane, lane_status)

    def update_lane_status(self, lane, status):
        """
        Update the status part of the UI, including the lane's color and status.
        """
        lane_box = self.lane_widgets.get(lane.name)
        logging.info(f"Updating lane status for {lane.name}: {status}")
        if not lane_box:
            logging.info(f"Lane box not found for lane: {lane.name}")
            return

        # Get the lane menu button widget
        lane_name = self.labels.get(f"{lane.name}")
        if not lane_name:
            logging.info(f"Lane menu button not found for lane: {lane.name}")
            return

        # Determine the new status color class
        status_color = self.set_lane_status(lane, status)

        # Update the style context of the lane menu button
        style_context = lane_name.get_style_context()

        # Remove all existing status-related classes
        style_context.remove_class("status-tooled")
        style_context.remove_class("status-loaded")
        style_context.remove_class("status-warning")
        style_context.remove_class("status-lane-empty")

        # Add the new status class
        for style in status_color:
            style_context.add_class(style)
            # logging.info(f"Updated lane {lane.name} to status: {status} with color class: {status_color}")

        # Force a redraw of the lane box
        lane_box.show()

    def update_lane_map(self, lane):
        """
        Update the map part of the UI, refreshing the dropdown to reflect the new mapping.
        """
        lane_map_widget = self.labels.get(f"{lane.name}_map_menu_button")
        if lane_map_widget:
            label = lane_map_widget.get_child()
            if label:
                label.set_text(lane.map)

    def update_lane_runout(self, lane):
        # Update the runout lane part of the UI
        runout_button = self.buttons.get(f"{lane.name}_runout_button")
        if runout_button:
            runout_button.set_label(f"{lane.runout_lane} ∞")

    def update_lane_material(self, lane):
        # Update the material part of the UI
        material_label = self.labels.get(f"{lane.name}_material_label")
        if material_label:
            material_label.set_label(f"{lane.material}")

    def update_lane_weight(self, lane):
        # Update the weight part of the UI
        weight_label = self.labels.get(f"{lane.name}_weight_label")
        if weight_label:
            weight_label.set_label(f"{lane.weight}g")
            self.update_lane_color(lane)  # Update the lane icon based on weight

    def update_lane_color(self, lane):
        lane._icon = None  # Clear the cached icon
        icon_button = self.buttons.get(f"{lane.name}_icon_button")
        if icon_button:
            icon = Gtk.Image.new_from_pixbuf(lane.icon(width=40,height=70))
            icon_button.set_image(icon)
            logging.info(f"replacing icon {icon}")
            icon_button.show_all()

    def update_lane_load(self, lane):
        # Update the load part of the UI
        # Assuming there's a widget or method to update the load status
        # lane_box.show_all()
        pass

    def update_system_container(self):
        """
        Update the labels for the current load, extruder, and buffer in the UI.
        If any value is None, display 'N/A'.
        """
        loaded_label = self.labels.get("loaded_label")
        extruder_label = self.labels.get("extruder_label")
        buffer_label = self.labels.get("buffer_label")

        # Check if current_load is None
        if not self.afc_system or not self.afc_system.current_load:
            # Set all labels to "N/A" if current_load is None
            if loaded_label:
                loaded_label.set_label("Loaded: N/A")
            if extruder_label:
                extruder_label.set_label("Extruder: N/A")
            if buffer_label:
                buffer_label.set_label("Buffer: N/A")
            return

        # Get the current lane object
        current_lane = next((lane for lane in self.afc_lane_data if lane.name == self.afc_system.current_load), None)

        # Update the loaded label
        if loaded_label:
            loaded_text = f"Loaded: {self.afc_system.current_load}" if self.afc_system.current_load else "Loaded: N/A"
            loaded_label.set_label(loaded_text)

        # Update the extruder label
        if extruder_label:
            extruder_text = f"Extruder: {current_lane.extruder}" if current_lane and current_lane.extruder else "Extruder: N/A"
            extruder_label.set_label(extruder_text)

        # Update the buffer label
        if buffer_label:
            buffer_text = f"Buffer: {current_lane.buffer} - {current_lane.buffer_status}" if current_lane and current_lane.buffer and current_lane.buffer_status else "Buffer: N/A"
            buffer_label.set_label(buffer_text)

    def on_lane_map_changed(self, menu_button, selected_value, lane, label):
        """
        Triggered when a new lane mapping is selected from the MenuButton.

        :param menu_button: The Gtk.MenuButton widget.
        :param selected_value: The T-value selected (e.g., "T0").
        :param lane: The current lane object.
        :param label: The label inside the MenuButton that displays the current value.
        """
        if selected_value and selected_value != lane.map:
            old_mapping = lane.map
            lane.map = selected_value  # Update lane map

            logging.info(f"Updated default mapping for {lane.name}: {old_mapping} → {selected_value}")

            # Update the label text in the MenuButton
            label.set_text(selected_value)

            # Send G-code to update the mapping
            self._screen._send_action(menu_button, "printer.gcode.script", {
                "script": f"SET_MAP LANE={lane.name} MAP={selected_value}"
            })

            # Optionally refresh UI
            self.refresh_lane_dropdowns()


    def refresh_lane_dropdowns(self):
        """
        Refresh all lane map dropdowns to reflect the current mappings.
        """
        for unit in self.afc_units:
            for lane in unit.lanes:
                self.update_lane_map(lane)

    def replace_lane_info_grid(self, lane, lane_name, status):
        old_grid = self.labels.get(f"{lane.name}_lane_info_grid")
        if old_grid:
            parent = old_grid.get_parent()
            if parent:
                parent.remove(old_grid)

        new_grid = self.create_lane_info_grid(lane, lane_name, status)
        if parent:
            parent.add(new_grid)
            new_grid.show_all()

    def update_lane_ui(self, lane):
        lane_box = self.lane_widgets.get(lane.name)
        if not lane_box:
            return

        # Update lane info box
        self.update_lane_info_box(lane)

        lane_box.show_all()


    ##################
    #    Callbacks   #
    ##################

    def on_lane_button_clicked(self, button, lane):
        logging.info(f"Lane button clicked: {lane.name}, status: {lane.status}")
        
        if lane.status in ("loaded", "tooled"):
            popup = PopupWindow(self, self.grid.get_toplevel(), lane)
            popup.show_all()
        else:
            return

    def on_icon_button_clicked(self, button, lane):
        print(f"Icon button clicked for lane: {lane.name}")

    def on_map_button_clicked(self, button, lane):
        print(f"Map button clicked: {lane.map}")

    def on_lane_inf_changed(self, menu_button, value, lane, label):
        if value and value != lane.map:
            old_runout = lane.runout_lane
            lane.runout_lane = value  # Update lane map
            logging.info(f"Updated default mapping for {lane.name}: {old_runout} → {value}")
            label.set_text(f"{value} ∞")


            # Send G-code to update the mapping
            self._screen._send_action(menu_button, "printer.gcode.script", {
                "script": f"SET_RUNOUT LANE={lane.name} RUNOUT={value}"
            })


    def on_load_lane_clicked(self, button, lane):
        logging.info(f"Load Lane button clicked for {lane.name}")
        self._screen._send_action(button, "printer.gcode.script", {"script": f"CHANGE_TOOL LANE={lane.name}"})

    def on_eject_lane_clicked(self, button, lane):
        logging.info(f"Eject Lane button clicked for {lane.name}")
        self._screen._send_action(button, "printer.gcode.script", {"script": f"LANE_UNLOAD LANE={lane.name}"})

    def on_unload_lane_clicked(self, button, lane):
        logging.info(f"Unload Lane button clicked for {lane.name}")
        self._screen._send_action(button, "printer.gcode.script", {"script": f"TOOL_UNLOAD"})

    #################
    #    Status     #
    #################

    def get_lane_status(self, lane):
        if lane.tool_loaded:
            status = "tooled"
        elif lane.prep and lane.load and not lane.tool_loaded:
            status = "loaded"
        elif lane.prep and not lane.load:
            status = "prep not load"
        elif lane.load and not lane.prep:
            status = "load not prep"
        else: 
            status = "unloaded"

        return status

    def get_lane_status_from_data(self, lane_data):
        if lane_data.get("tool_loaded"):
            return "tooled"
        elif lane_data.get("prep") and lane_data.get("load") and not lane_data.get("tool_loaded"):
            return "loaded"
        elif lane_data.get("prep") and not lane_data.get("load"):
            return "prep not load"
        elif lane_data.get("load") and not lane_data.get("prep"):
            return "load not prep"
        else:
            return "unloaded"

    def set_lane_status(self, lane, status):
        logging.info(f"Lane {lane.name} status: {status}")
        style = []
        if status == "tooled":
            style.append("status-tooled")
            style.append("bold-text")
        elif status == "loaded":
            style.append("status-loaded")
        elif status == "prep not load":
            style.append("status-warning")
        elif status == "load not prep":
            style.append("status-warning")
        else:
            style.append("status-lane-empty")

        return style

    ##################
    #    Dropdowns   #
    ##################

    def create_lane_dropdown(self):
        """
        Create a dropdown (Gtk.ComboBox) for selecting lanes with enhanced behavior.
        """
        # Create a ListStore to hold the lane names
        lane_store = Gtk.ListStore(str)
        for lane in self.get_afc_lanes():
            lane_store.append([lane])  # Add each lane name to the store

        # Create the dropdown
        dropdown = Gtk.ComboBox.new_with_model(lane_store)
        dropdown.set_vexpand(True)
        renderer_text = Gtk.CellRendererText()
        dropdown.pack_start(renderer_text, True)
        dropdown.add_attribute(renderer_text, "text", 0)
        dropdown.set_active(0)  # Set the first lane as the default selection

        dropdown.set_direction(Gtk.ArrowType.UP)

        # Set the default move_lane to the first lane
        if self.afc_lanes:
            self.move_lane = self.afc_lanes[0]

        # Connect the "changed" signal to handle lane selection
        dropdown.connect("changed", self.on_lane_selected)

        # Connect the "notify::popup-shown" signal to handle dropdown behavior
        dropdown.connect("notify::popup-shown", self.on_popup_shown)

        # Add a label above the dropdown
        dropdown_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        dropdown_box.pack_start(dropdown, False, False, 0)

        self.dropdown = dropdown  # Store the dropdown for later use
        self.last_drop_time = None  # Track the last time the dropdown was opened

        return dropdown_box

    def create_distance_grid(self):
        """
        Create a grid of buttons to select the move distance.
        """
        distbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.labels['move_dist'] = Gtk.Label(label="Distance (mm)")
        self.labels['move_dist'].set_halign(Gtk.Align.CENTER)
        distbox.pack_start(self.labels['move_dist'], True, True, 0)
        distbox.set_margin_bottom(25)

        distance_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        distance_box.set_halign(Gtk.Align.CENTER)

        # Create the distance entry and add it to self.labels
        self.labels['distance_entry'] = Gtk.Entry()
        self.labels['distance_entry'].set_hexpand(True)
        self.labels['distance_entry'].set_placeholder_text("Enter distance")
        self.labels['distance_entry'].set_text(str(self.distance))
        self.labels['distance_entry'].set_valign(Gtk.Align.FILL)
        self.labels['distance_entry'].set_halign(Gtk.Align.CENTER)
        self.labels['distance_entry'].set_size_request(150, -1)
        self.labels['distance_entry'].set_width_chars(4)
        self.labels['distance_entry'].set_input_purpose(Gtk.InputPurpose.NUMBER)
        self.labels['distance_entry'].connect("focus-in-event", self.show_keyboard)
        self.labels['distance_entry'].connect("focus-out-event", self._screen.remove_keyboard)
        self.labels['distance_entry'].connect("changed", self.on_distance_changed)
        distance_box.pack_start(self.labels['distance_entry'], True, True, 0)

        # Create the distance grid
        distgrid = Gtk.Grid(column_homogeneous=True)
        distgrid.set_column_spacing(1)
        self.distances = ['5', '10', '25', '50']  # Define available distances
        for j, i in enumerate(self.distances):
            self.labels[f"dist{i}"] = Gtk.Button(label=i)
            self.labels[f"dist{i}"].connect("clicked", self.change_distance, int(i))
            ctx = self.labels[f"dist{i}"].get_style_context()
            ctx.add_class("horizontal_togglebuttons")
            if int(i) == self.distance:
                ctx.add_class("horizontal_togglebuttons_active")
            distgrid.attach(self.labels[f"dist{i}"], (j+1), 0, 1, 1)
            self.labels[f"dist{i}"].set_hexpand(True)

        distance_box.pack_start(distgrid, True, True, 0)
        distbox.add(distance_box)
        return distbox

    def on_distance_changed(self, entry):
        """
        Handle distance entry changes and update the grid selection.
        """
        distance = int(entry.get_text())
        if distance > 0:
            self.distance = distance

            # Highlight the corresponding button if it matches a predefined distance
            for dist in self.distances:
                button = self.labels.get(f"dist{dist}")
                if button:
                    ctx = button.get_style_context()
                    if int(dist) == distance:
                        ctx.add_class("horizontal_togglebuttons_active")
                    else:
                        ctx.remove_class("horizontal_togglebuttons_active")
        else:
            # Clear highlights if the input is invalid
            self.clear_grid_selection()

    def change_distance(self, widget, distance):
        """
        Update the selected distance and highlight the active button.
        """
        # Remove the active class from the previously selected button
        previous_button = self.labels.get(f"dist{self.distance}")
        if previous_button:
            previous_button.get_style_context().remove_class("horizontal_togglebuttons_active")

        # Add the active class to the newly selected button
        widget.get_style_context().add_class("horizontal_togglebuttons_active")

        # Update the distance and the entry
        self.distance = distance
        self.labels['distance_entry'].set_text(str(distance))

    def clear_grid_selection(self):
        """
        Clear the selection in the grid.
        """
        for dist in ['5', '10', '25', '50']:
            button = self.labels.get(f"dist{dist}")
            if button:
                button.get_style_context().remove_class("horizontal_togglebuttons_active")

    def on_lane_selected(self, dropdown):
        """
        Handle lane selection from the dropdown and update self.move_lane.
        """
        model = dropdown.get_model()
        active_iter = dropdown.get_active_iter()
        if active_iter is not None:
            self.move_lane = model[active_iter][0]  # Update the selected lane
            logging.info(f"Selected lane: {self.move_lane}")
        else:
            logging.warning("No lane selected.")

    def on_popup_shown(self, combo_box, param):
        """
        Handle the dropdown's popup-shown signal to detect when it opens or closes.
        """
        if combo_box.get_property("popup-shown"):
            logging.debug("Dropdown popup show")
            self.last_drop_time = datetime.now()
        else:
            elapsed = (datetime.now() - self.last_drop_time).total_seconds()
            if elapsed < 0.2:  # If the dropdown closes too quickly
                logging.debug(f"Dropdown closed too fast ({elapsed}s)")
                GLib.timeout_add(50, self.dropdown_keep_open)
                return
            logging.debug("Dropdown popup close")

    def dropdown_keep_open(self):
        """
        Reopen the dropdown if it closes too quickly.
        """
        self.dropdown.popup()
        return False

    def on_move_button_clicked(self, button):
        """
        Handle the move button click and send the move command.
        """
        if not self.move_lane:
            logging.warning("Move command failed: No lane selected.")
            return

        logging.info(f"Moving to lane: {self.move_lane} with distance: {self.distance}")
        self._screen._send_action(button, "printer.gcode.script", {
            "script": f"LANE_MOVE LANE={self.move_lane} DISTANCE={self.distance}"
        })

    def on_neg_move_button_clicked(self, button):
        """
        Handle the move button click and send the move command.
        """
        if not self.move_lane:
            logging.warning("Move command failed: No lane selected.")
            return

        logging.info(f"Moving to lane: {self.move_lane} with distance: {self.distance}")
        self._screen._send_action(button, "printer.gcode.script", {
            "script": f"LANE_MOVE LANE={self.move_lane} DISTANCE=-{self.distance}"
        })

    ##################
    # Spool Selector #
    ##################

    def create_spool_layout(self):
        """
        Create a layout for changing the spool, including input boxes in a scroll box,
        and dynamically show/hide the keyboard or keypad.
        """
        logging.info("Creating spool selector layout")

        self.input_widgets = {}

        # Main container
        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        main_box.set_hexpand(True)
        main_box.set_vexpand(True)

        # Scrollable container for input boxes
        self.spool_scroll = Gtk.ScrolledWindow()
        self.spool_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.spool_scroll.set_hexpand(True)
        self.spool_scroll.set_vexpand(True)

        input_grid = AutoGrid()
        input_grid.set_row_homogeneous(False)
        input_grid.set_column_homogeneous(False)
        input_grid.set_row_spacing(10)
        input_grid.set_column_spacing(20)
        input_grid.set_margin_top(20)
        input_grid.set_margin_bottom(20)
        input_grid.set_margin_start(20)
        input_grid.set_margin_end(20)

        # Title
        title_label = Gtk.Label(label="Change Spool")
        title_label.set_halign(Gtk.Align.CENTER)
        title_label.set_valign(Gtk.Align.CENTER)
        title_label.get_style_context().add_class("bold-text")
        self.labels['title_label'] = title_label  # Store the title label
        input_grid.attach(title_label, 0, 0, 2, 1)  # Span across two columns
        self.labels["title_label"].grab_focus

        # Color Selector
        color_label = Gtk.Label(label="Filament Color")
        color_label.set_halign(Gtk.Align.START)
        color_label.set_valign(Gtk.Align.CENTER)
        color_label.get_style_context().add_class("bold-text")

        color_selector = self.create_color_selector()
        color_selector.set_hexpand(False)
        # color_selector.set_halign(Gtk.Align.START)
        input_grid.attach(color_label, 0, 1, 1, 1)
        input_grid.attach(color_selector, 1, 1, 1, 1)

        # Filament Type Selector
        type_label = Gtk.Label(label="Filament Type")
        type_label.set_halign(Gtk.Align.START)
        type_label.set_valign(Gtk.Align.CENTER)
        type_label.get_style_context().add_class("bold-text")
        type_input = Gtk.Entry()
        type_input.set_hexpand(True)
        # type_input.set_halign(Gtk.Align.START)
        type_input.set_placeholder_text("Enter filament type (e.g., PLA)")
        type_input.connect("focus-in-event", self.show_keyboard)
        type_input.connect("focus-out-event", self._screen.remove_keyboard)
        self.labels["type_input"] = type_input  # Store the input widget
        input_grid.attach(type_label, 0, 2, 1, 1)
        input_grid.attach(type_input, 1, 2, 1, 1)

        # Weight Input
        weight_label = Gtk.Label(label="Remaining Weight")
        weight_label.set_halign(Gtk.Align.START)
        weight_label.set_valign(Gtk.Align.CENTER)
        weight_label.get_style_context().add_class("bold-text")
        weight_input = Gtk.Entry()
        weight_input.set_hexpand(True)
        # weight_input.set_halign(Gtk.Align.START)
        weight_input.set_placeholder_text("Enter weight (e.g., 700)")
        weight_input.set_input_purpose(Gtk.InputPurpose.NUMBER)
        weight_input.connect("focus-in-event", self.show_keyboard)
        weight_input.connect("focus-out-event", self._screen.remove_keyboard)
        self.labels["weight_input"] = weight_input  # Store the input widget
        input_grid.attach(weight_label, 0, 3, 1, 1)
        input_grid.attach(weight_input, 1, 3, 1, 1)

        # Buttons
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        button_box.set_halign(Gtk.Align.CENTER)
        button_box.set_hexpand(False)
        button_box.set_vexpand(False)
        return_button = self._gtk.Button("back", _("Return"), "color2")
        return_button.set_halign(Gtk.Align.CENTER)
        return_button.set_valign(Gtk.Align.CENTER)
        return_button.connect("clicked", self.show_main_grid)
        button_box.pack_start(return_button, True, True, 5)

        update_button = self._gtk.Button("complete", _("Update"), "color1", scale=1.5)
        update_button.set_halign(Gtk.Align.CENTER)
        update_button.set_valign(Gtk.Align.CENTER)
        update_button.connect("clicked", self.on_update_spool_clicked)
        button_box.pack_start(update_button, True, True, 5)

        weight_input.connect("changed", self.on_weight_changed)
        type_input.connect("changed", self.on_type_changed)

        input_grid.attach(button_box, 0, 4, 2, 1)  # Span across two columns

        # Add input grid to the scroll container
        self.spool_scroll.add(input_grid)

        main_box.pack_start(self.spool_scroll, True, True, 5)

        # Attach the overlay to the selector grid
        self.selector_grid.attach(main_box, 0, 0, 1, 1)

    def on_weight_changed(self, entry):
        self.selected_weight = entry.get_text()

    def on_type_changed(self, entry):
        self.selected_type = entry.get_text()

    def show_keyboard(self, entry, event):
        self._screen.show_keyboard(entry, event)
        GLib.timeout_add(100, self.scroll_to_entry, entry)

    def scroll_to_entry(self, entry):
        """
        Scroll the view to ensure the specified entry is visible.
        """
        if self.spool_scroll:
            adjustment = self.spool_scroll.get_vadjustment()
            allocation = entry.get_allocation()
            adjustment.set_value(allocation.y - 50)  # Adjust the scroll position

    def create_color_selector(self):
        """
        Create a touch-friendly color selector for the filament.
        """
        color_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        color_box.set_hexpand(False)
        color_selector_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        # RGB input fields
        rgb_box = Gtk.Grid()
        rgb_box.set_column_homogeneous(False)
        rgb_box.set_row_spacing(5)
        rgb_box.set_column_spacing(5)

        self.r_input = Gtk.Entry()
        self.r_input.set_hexpand(True)
        self.r_input.set_input_purpose(Gtk.InputPurpose.NUMBER)
        self.r_input.connect("focus-in-event", self.show_keyboard)
        self.r_input.connect("focus-out-event", self._screen.remove_keyboard)
        self.r_input.set_placeholder_text("R")
        self.r_input.set_width_chars(3)

        self.g_input = Gtk.Entry()
        self.g_input.set_hexpand(True)
        self.g_input.set_input_purpose(Gtk.InputPurpose.NUMBER)
        self.g_input.connect("focus-in-event", self.show_keyboard)
        self.g_input.connect("focus-out-event", self._screen.remove_keyboard)
        self.g_input.set_placeholder_text("G")
        self.g_input.set_width_chars(3)

        self.b_input = Gtk.Entry()
        self.b_input.set_hexpand(True)
        self.b_input.connect("focus-in-event", self.show_keyboard)
        self.b_input.connect("focus-out-event", self._screen.remove_keyboard)
        self.b_input.set_input_purpose(Gtk.InputPurpose.NUMBER)
        self.b_input.set_placeholder_text("B")
        self.b_input.set_width_chars(3)

        self.r_input.connect("changed", self.on_rgb_changed)
        self.g_input.connect("changed", self.on_rgb_changed)
        self.b_input.connect("changed", self.on_rgb_changed)

        rgb_box.attach(Gtk.Label(label="R:"), 0, 0, 1, 1)
        rgb_box.attach(self.r_input, 1, 0, 1, 1)
        rgb_box.attach(Gtk.Label(label="G:"), 2, 0, 1, 1)
        rgb_box.attach(self.g_input, 3, 0, 1, 1)
        rgb_box.attach(Gtk.Label(label="B:"), 4, 0, 1, 1)
        rgb_box.attach(self.b_input, 5, 0, 1, 1)

        color_selector_box.pack_start(rgb_box, True, True, 0)

        # HEX input field
        hex_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        hex_label = Gtk.Label(label="HEX:")
        hex_label.get_style_context().add_class("bold-text")
        self.hex_input = Gtk.Entry()
        self.hex_input.connect("changed", self.on_hex_changed)
        self.hex_input.connect("focus-in-event", self.show_keyboard)
        self.hex_input.connect("focus-out-event", self._screen.remove_keyboard)
        self.hex_input.set_placeholder_text("#RRGGBB")
        self.hex_input.set_width_chars(7)

        # Color preview and button
        self.color_button = Gtk.ColorButton()  # Store a reference to the color buttons
        self.color_button.get_style_context().add_class("color-button")
        self.color_button.set_title("Select Filament Color")
        self.color_button.set_rgba(Gdk.RGBA(1, 0, 0, 1))  # Default to red
        self.color_button.set_use_alpha(False)
        self.color_button.set_size_request(200, 75)
        self.color_button.connect("color-set", self.on_color_selected)

        hex_box.pack_start(hex_label, False, False, 0)
        hex_box.pack_start(self.hex_input, True, True, 0)
        color_selector_box.pack_start(hex_box, False, False, 0)
        color_box.pack_start(self.color_button, True, True, 0)
        color_box.pack_start(color_selector_box, True, True, 0)

        return color_box

    def on_rgb_changed(self, entry):
        """
        Update the color button and HEX field when RGB values are changed.
        """
        try:
            r = int(self.r_input.get_text() or 0)
            g = int(self.g_input.get_text() or 0)
            b = int(self.b_input.get_text() or 0)

            # Clamp values between 0 and 255
            r = max(0, min(255, r))
            g = max(0, min(255, g))
            b = max(0, min(255, b))

            # Update the color button
            self.color_button.set_rgba(Gdk.RGBA(r / 255, g / 255, b / 255, 1))

            # Update the HEX field
            self.selected_color = f"#{r:02X}{g:02X}{b:02X}"
            self.hex_input.set_text(self.selected_color)
        except ValueError:
            pass  # Ignore invalid input

    def on_hex_changed(self, entry):
        """
        Update the color button and RGB fields when the HEX value is changed.
        """
        hex_value = entry.get_text().lstrip("#")
        if len(hex_value) == 6:
            try:
                r = int(hex_value[0:2], 16)
                g = int(hex_value[2:4], 16)
                b = int(hex_value[4:6], 16)

                # Update the color button
                self.color_button.set_rgba(Gdk.RGBA(r / 255, g / 255, b / 255, 1))

                # Update the RGB fields
                self.r_input.set_text(str(r))
                self.g_input.set_text(str(g))
                self.b_input.set_text(str(b))
            except ValueError:
                pass  # Ignore invalid HEX values


    def on_color_selected(self, color_button):
        """
        Update the RGB and HEX fields when a color is selected from the color button.
        """
        rgba = color_button.get_rgba()
        r = int(rgba.red * 255)
        g = int(rgba.green * 255)
        b = int(rgba.blue * 255)

        # Update RGB fields
        self.r_input.set_text(str(r))
        self.g_input.set_text(str(g))
        self.b_input.set_text(str(b))

        # Update HEX field
        self.selected_color = f"#{r:02X}{g:02X}{b:02X}"
        self.hex_input.set_text(self.selected_color)

    def on_update_spool_clicked(self, button):
        """
        Handle the 'Update Spool' button click event.
        """
        logging.info(f"Update Spool button clicked with color: {self.selected_color}")

        if self.spoolman is not None:
            self._screen._send_action(button, "printer.gcode.script", {
                "script": f'SET_SPOOL_ID LANE={self.selected_lane.name} SPOOL_ID=""'
            })

        # Handle color
        try:
            color = self.selected_color.lstrip("#")
            if color:
                self._screen._send_action(button, "printer.gcode.script", {
                    "script": f"SET_COLOR LANE={self.selected_lane.name} COLOR={color}"
                })
        except AttributeError:
            logging.warning("Selected color is not set or invalid. Skipping color update.")

        # Handle filament type
        try:
            filament_type = self.selected_type
            if filament_type:
                self._screen._send_action(button, "printer.gcode.script", {
                    "script": f"SET_MATERIAL LANE={self.selected_lane.name} MATERIAL={filament_type.upper()}"
                })
        except AttributeError:
            logging.warning("Selected filament type is not set or invalid. Skipping material update.")

        # Handle weight
        try:
            weight = self.selected_weight
            if weight:
                self._screen._send_action(button, "printer.gcode.script", {
                    "script": f"SET_WEIGHT LANE={self.selected_lane.name} WEIGHT={weight}"
                })
        except AttributeError:
            logging.warning("Selected weight is not set or invalid. Skipping weight update.")

        # Handle lane
        try:
            lane = self.selected_lane
            if not lane:
                logging.warning("Selected lane is not set or invalid. Skipping lane update.")
        except AttributeError:
            logging.warning("Selected lane is not set or invalid. Skipping lane update.")

        # Return to the main grid
        self.show_main_grid(button)

    ##################
    #    Sensors     #
    ##################

    def sensor_layout(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)

        self.sensor_labels = {}

        screen_width = self._screen.width
        # Fetch the current sensor states before passing to create_sensor_grid
        sensor_data = self.fetch_sensor_data()
        sensors_grid = self.create_sensor_grid(self.filament_sensors, screen_width, sensor_data)
        vbox.pack_start(sensors_grid, True, True, 0)

        refresh_button = Gtk.Button(label="Refresh")
        refresh_button.get_style_context().add_class("button_active")
        refresh_button.connect("clicked", self.on_refresh_clicked)
        vbox.pack_start(refresh_button, False, False, 0)

        self.sensor_grid.attach(vbox, 0, 0, 1, 1)

    def create_sensor_grid(self, sensors, screen_width, sensor_data):
        # Main grid
        grid = AutoGrid()
        grid.set_hexpand(True)
        grid.set_vexpand(True)
        grid.set_column_spacing(20)  # Add more space between columns
        grid.set_row_spacing(5)
        grid.set_column_homogeneous(False)

        # Custom sorting function
        def sensor_sort_key(sensor_name):
            # Assign priorities based on sensor type
            if "prep" in sensor_name.lower():
                priority = 0  # Highest priority for "prep" sensors
            elif "load" in sensor_name.lower():
                priority = 1  # Second priority for "load" sensors
            else:
                priority = 2  # Lowest priority for other sensors

            # Extract the numeric part of the sensor name for secondary sorting
            match = re.search(r'\d+', sensor_name)
            numeric_part = int(match.group()) if match else float('inf')

            # Return a tuple for sorting: (priority, numeric part)
            return (priority, numeric_part)

        # Sort sensors using the custom key
        sensors = sorted(sensors, key=sensor_sort_key)

        # Group sensors into "prep", "load", and "others"
        prep_sensors = [s for s in sensors if "prep" in s.lower()]
        load_sensors = [s for s in sensors if "load" in s.lower()]
        other_sensors = [s for s in sensors if s not in prep_sensors and s not in load_sensors]

        # Arrange sensors into columns
        columns = [prep_sensors, load_sensors, other_sensors]

        for col_index, column in enumerate(columns):
            for row_index, sensor_name in enumerate(column):
                label_name = sensor_name.split("filament_switch_sensor ", 1)[-1].strip()
                label_name = label_name.replace("_", " ").capitalize()

                # Create the sensor label
                sensor_label = Gtk.Label(label=label_name)
                sensor_label.set_halign(Gtk.Align.END)
                sensor_label.set_hexpand(False)

                # Create the status dot
                status_dot = Gtk.EventBox()
                dot = Gtk.Label(label=" ")
                dot.set_size_request(20, 20)
                dot.set_valign(Gtk.Align.CENTER)
                dot.set_halign(Gtk.Align.START)

                style = dot.get_style_context()
                filament_detected = sensor_data.get(sensor_name, {}).get("filament_detected", False)
                style.remove_class("status-empty")
                style.remove_class("status-active")
                style.add_class("status-active" if filament_detected else "status-empty")

                status_dot.add(dot)

                # Store the label and dot for updates
                self.sensor_labels[sensor_name] = {"label": sensor_label, "dot": dot}

                # Attach the label and dot to the grid
                grid.attach(sensor_label, col_index * 3, row_index, 1, 1)  # Name column
                grid.attach(status_dot, col_index * 3 + 1, row_index, 1, 1)  # Dot column

        # Add the grid to a scrolled window
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_hexpand(True)
        scrolled_window.set_vexpand(True)
        scrolled_window.add(grid)

        # Create Return button
        return_button = self._gtk.Button("back", _("Back"), "color3")
        return_button.set_halign(Gtk.Align.END)
        return_button.set_valign(Gtk.Align.START)
        return_button.set_margin_top(10)
        return_button.set_margin_end(10)

        return_button.connect("clicked", self.show_main_grid)  # Define this handler in your class

        # Overlay button on top of the scrolled window
        overlay = Gtk.Overlay()
        overlay.set_hexpand(True)
        overlay.set_vexpand(True)
        overlay.add(scrolled_window)
        overlay.add_overlay(return_button)

        return overlay

    def fetch_sensor_data(self):
        """
        Fetches the current filament sensor data from the printer API.
        :return: Dictionary containing the status of the sensors.
        """
        # Here we send the request and parse the result into a dictionary
        sensor_query = "&".join(self.filament_sensors)
        result = self.apiClient.send_request(f"printer/objects/query?{sensor_query}")
        sensor_data = result.get("status", {})
        return sensor_data

    def update_sensors(self, data):
        """
        Updates the sensor dots based on the latest data.
        :param data: The latest sensor data from the API.
        """
        for sensor_name, elements in self.sensor_labels.items():
            dot = elements["dot"]
            sensor_data = data.get(sensor_name)
            if sensor_data and isinstance(sensor_data, dict):
                detected = sensor_data.get("filament_detected", False)
                style = dot.get_style_context()
                style.remove_class("status-empty")
                style.remove_class("status-active")
                style.add_class("status-active" if detected else "status-empty")

    def on_refresh_clicked(self, button):
        """
        Handles the refresh button click event to update the sensor states.
        :param button: The refresh button widget.
        """
        if not self.filament_sensors:
            return
        # Fetch the latest sensor data
        sensor_data = self.fetch_sensor_data()
        # Update the sensor grid
        self.update_sensors(sensor_data)


###################
#    CSS Styles   #
###################

# Additional CSS to style the lane boxes
inline_provider = Gtk.CssProvider()
inline_provider.load_from_data(b"""
dialog {
    background-color: rgba(100, 100, 100, 0.85);
    color: white;
}
dialog label {
    color: white;
}
dialog button {
    background-color: rgba(20, 20, 20, 0.85);
    color: white;
    border-radius: 10px;
}
.scroll_button{
    background-color: rgba(35, 35, 35, 0.85);
}
.bold-text {
    font-weight: bold;
}
.large-button {
    font-size: 20px;
    padding-left: 40px;
    padding-right: 40px;
    padding-top: 10px;
    padding-bottom: 10px;
}
.small-scroll {
    -GtkScrollbar-width: 2px;
}
.color-button {
    border: 2px solid #ffffff;
    border-radius: 20px;
    padding: 10px;
    margin: 10px;
}
.close-box {
    background-color: rgba(128, 40, 40, 0.90);
    border-radius: 5px;
    padding: 10px;
}
.extruder-box {
    background-color: rgba(50, 50, 50, 0.4);
    border-radius: 8px;
    padding: 10px;
}
.lane-box {
    background-color: rgba(70, 70, 70, 0.7);
    border-radius: 8px;
    padding: 4px;
}
.header-box {
    background-color: rgba(70, 70, 70, 0.7);
    border-radius: 8px;
    padding: 10px;
    color: rgb(0,0,0);
}
.load-box {
    background-color: rgba(40, 40, 40, 0.90);
    border-radius: 8px;
    min-height: 250px;
}
.lane-back {
    background-color: rgba(50, 50, 50, 0.85);
    border-radius: 5px;
    padding: 5px;
}
.action-button {
    background-color: rgba(50, 50, 50, 0.85);
    border-color: @color3;
    border-style: solid;
    border-width: 4px;
    border-radius: 8px;
    padding-top: 15px;
    padding-bottom: 15px;
}
.action-button-small {
    background-color: rgba(50, 50, 50, 0.85);
    border-color: @color3;
    border-style: solid;
    border-width: 4px;
    border-radius: 8px;
    padding: 5px;
}
.no-background {
    background-color: rgba(50, 50, 50, 0.0);
    border-radius: 5px;
}
.highlighted-lane {
    border: 2px solid #429ef5;
    border-radius: 1em;
    border-width: 4px;
}
.status-loaded {
    color: #48bf53; /* Replace @color3 with a valid color */
}
.status-lane-empty {
    color: #e32929; /* Replace @color1 with a valid color */
}
.status-warning {
    color: #eb8510; /* Replace @color4 with a valid color */
}
.status-tooled {
    color: #429ef5;
}
.combo-no-arrow box arrow {
    padding: 0px;
    margin: 0;
    opacity: 0;
    min-width: 0;
    min-height: 0;
}
.filament_sensor_empty {
    background-color: @active; /* Red for empty */
}
.filament_sensor_detected {
    background-color: @echo; /* Green for detected */
}
.status-active {
    background-color: #48bf53;
    border-radius: 25px;
}
.status-empty {
    background-color: #e32929;
    border-radius: 25px;
}
""")

Gtk.StyleContext.add_provider_for_screen(
    Gdk.Screen.get_default(),
    inline_provider,
    Gtk.STYLE_PROVIDER_PRIORITY_USER
)

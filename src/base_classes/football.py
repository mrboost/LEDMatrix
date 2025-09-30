from typing import Dict, Any, Optional, List
from src.display_manager import DisplayManager
from src.cache_manager import CacheManager
from datetime import datetime, timezone, timedelta
import logging
from PIL import Image, ImageDraw, ImageFont
import time
import random
import pytz
from src.base_classes.sports import SportsCore
from src.base_classes.api_extractors import ESPNFootballExtractor
from src.base_classes.data_sources import ESPNDataSource
import requests

# ================================
# NFL TEAM COLORS for Scoring Alerts
# ================================
NFL_TEAM_COLORS = {
    "TB": ((213, 10, 10), (101, 79, 73)),
    "DAL": ((0, 34, 68), (134, 147, 151)),
    "KC": ((227, 24, 55), (255, 184, 28)),
    "BUF": ((0, 51, 141), (198, 12, 48)),
    "MIA": ((0, 142, 151), (252, 76, 2)),
    "NE": ((0, 34, 68), (198, 12, 48)),
    "NYJ": ((18, 87, 64), (255, 255, 255)),
    "LV": ((0, 0, 0), (165, 172, 175)),
    "DEN": ((251, 79, 20), (0, 34, 68)),
    "LAC": ((0, 128, 198), (255, 194, 14)),
    "PHI": ((0, 76, 84), (165, 172, 175)),
    "NYG": ((1, 35, 82), (163, 13, 45)),
    "WSH": ((90, 20, 20), (255, 182, 18)),
    "GB": ((24, 48, 40), (255, 184, 28)),
    "CHI": ((11, 22, 42), (200, 56, 3)),
    "MIN": ((79, 38, 131), (255, 198, 47)),
    "DET": ((0, 118, 182), (176, 183, 188)),
    "SF": ((170, 0, 0), (173, 153, 93)),
    "SEA": ((0, 34, 68), (105, 190, 40)),
    "LAR": ((0, 53, 148), (255, 209, 0)),
    "ARI": ((155, 35, 63), (255, 182, 18)),
    "NO": ((16, 24, 31), (211, 188, 141)),
    "ATL": ((167, 25, 48), (0, 0, 0)),
    "CAR": ((0, 133, 202), (16, 24, 31)),
    "PIT": ((16, 24, 32), (255, 182, 18)),
    "BAL": ((26, 25, 95), (158, 124, 12)),
    "CIN": ((251, 79, 20), (0, 0, 0)),
    "CLE": ((49, 29, 0), (255, 60, 0)),
    "TEN": ((12, 35, 64), (75, 146, 219)),
    "IND": ((0, 44, 95), (255, 255, 255)),
    "JAX": ((16, 24, 31), (215, 163, 62)),
    "HOU": ((3, 32, 47), (167, 25, 48)),
}

class Football(SportsCore):
    """Base class for football sports with common functionality."""
    
    def __init__(self, config: Dict[str, Any], display_manager: DisplayManager, cache_manager: CacheManager, logger: logging.Logger, sport_key: str):
        super().__init__(config, display_manager, cache_manager, logger, sport_key)
        
        # Initialize football-specific architecture components
        self.api_extractor = ESPNFootballExtractor(logger)
        self.data_source = ESPNDataSource(logger)
        self.sport = "football"

    def _extract_game_details(self, game_event: Dict) -> Optional[Dict]:
        """Extract relevant game details from ESPN NCAA FB API response."""
        details, home_team, away_team, status, situation = self._extract_game_details_common(game_event)
        if details is None or home_team is None or away_team is None or status is None:
            return
        try:
            competition = game_event["competitions"][0]
            status = competition["status"]

            # --- Football Specific Details (Likely same for NFL/NCAAFB) ---
            down_distance_text = ""
            possession_indicator = None # Default to None
            scoring_event = ""  # Track scoring events
            home_timeouts = 0
            away_timeouts = 0
            is_redzone = False
            posession = None

            if situation and status["type"]["state"] == "in":
                # down = situation.get("down")
                down_distance_text = situation.get("shortDownDistanceText")
                # long_text = situation.get("downDistanceText")
                # distance = situation.get("distance")
                
                # Detect scoring events from status detail
                status_detail = status["type"].get("detail", "").lower()
                status_short = status["type"].get("shortDetail", "").lower()
                is_redzone = situation.get("isRedZone")
                posession = situation.get("possession")
                
                # Check for scoring events in status text
                if any(keyword in status_detail for keyword in ["touchdown", "td"]):
                    scoring_event = "TOUCHDOWN"
                elif any(keyword in status_detail for keyword in ["field goal", "fg"]):
                    scoring_event = "FIELD GOAL"
                elif any(keyword in status_detail for keyword in ["extra point", "pat", "point after"]):
                    scoring_event = "PAT"
                elif any(keyword in status_short for keyword in ["touchdown", "td"]):
                    scoring_event = "TOUCHDOWN"
                elif any(keyword in status_short for keyword in ["field goal", "fg"]):
                    scoring_event = "FIELD GOAL"
                elif any(keyword in status_short for keyword in ["extra point", "pat"]):
                    scoring_event = "PAT"

                # Determine possession based on team ID
                possession_team_id = situation.get("possession")
                if possession_team_id:
                    if possession_team_id == home_team.get("id"):
                        possession_indicator = "home"
                    elif possession_team_id == away_team.get("id"):
                        possession_indicator = "away"

                home_timeouts = situation.get("homeTimeouts", 3) # Default to 3 if not specified
                away_timeouts = situation.get("awayTimeouts", 3) # Default to 3 if not specified


            # Format period/quarter
            period = status.get("period", 0)
            period_text = ""
            if status["type"]["state"] == "in":
                 if period == 0: period_text = "Start" # Before kickoff
                 elif period == 1: period_text = "Q1"
                 elif period == 2: period_text = "Q2"
                 elif period == 3: period_text = "Q3" # Fixed: period 3 is 3rd quarter, not halftime
                 elif period == 4: period_text = "Q4"
                 elif period > 4: period_text = "OT" # OT starts after Q4
            elif status["type"]["state"] == "halftime" or status["type"]["name"] == "STATUS_HALFTIME": # Check explicit halftime state
                period_text = "HALF"
            elif status["type"]["state"] == "post":
                 if period > 4 : period_text = "Final/OT"
                 else: period_text = "Final"
            elif status["type"]["state"] == "pre":
                period_text = details.get("game_time", "") # Show time for upcoming

            details.update({
                "period": period,
                "period_text": period_text, # Formatted quarter/status
                "clock": status.get("displayClock", "0:00"),
                "home_timeouts": home_timeouts,
                "away_timeouts": away_timeouts,
                "down_distance_text": down_distance_text, # Added Down/Distance
                "is_redzone": is_redzone,
                "possession": posession, # ID of team with possession
                "possession_indicator": possession_indicator, # Added for easy home/away check
                "scoring_event": scoring_event, # Track scoring events (TOUCHDOWN, FIELD GOAL, PAT)
            })

            # Basic validation (can be expanded)
            if not details['home_abbr'] or not details['away_abbr']:
                 self.logger.warning(f"Missing team abbreviation in event: {details['id']}")
                 return None

            self.logger.debug(f"Extracted: {details['away_abbr']}@{details['home_abbr']}, Status: {status['type']['name']}, Live: {details['is_live']}, Final: {details['is_final']}, Upcoming: {details['is_upcoming']}")

            return details
        except Exception as e:
            # Log the problematic event structure if possible
            logging.error(f"Error extracting game details: {e} from event: {game_event.get('id')}", exc_info=True)
            return None

class FootballLive(Football):
    def __init__(self, config: Dict[str, Any], display_manager: DisplayManager, cache_manager: CacheManager, logger: logging.Logger, sport_key: str):
        super().__init__(config, display_manager, cache_manager, logger, sport_key)
        self.update_interval = self.mode_config.get("live_update_interval", 15)
        self.no_data_interval = 300
        self.last_update = 0
        self.live_games = []
        self.current_game_index = 0
        self.last_game_switch = 0
        self.game_display_duration = self.mode_config.get("live_game_duration", 20)
        self.last_display_update = 0
        self.last_log_time = 0
        self.log_interval = 300
        
        # Scoring alerts tracking
        self.last_scoring_events = {}
        self.scoring_alerts_enabled = config.get(sport_key, {}).get('scoring_alerts', True)
        
        # Load font for scoring animations
        try:
            self.alert_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 12)
        except:
            self.alert_font = ImageFont.load_default()
    
    def _check_scoring_events(self):
        """Check all live games for scoring events and trigger animations."""
        if not self.scoring_alerts_enabled:
            return
        
        for game in self.live_games:
            game_id = game.get('id')
            scoring_event = game.get('scoring_event', '')
            
            if not scoring_event or not game_id:
                if game_id in self.last_scoring_events:
                    del self.last_scoring_events[game_id]
                continue
            
            # Check if this is a new scoring event
            if game_id in self.last_scoring_events and self.last_scoring_events[game_id] == scoring_event:
                continue
            
            # Update tracking
            self.last_scoring_events[game_id] = scoring_event
            
            # Determine which team scored
            possession_id = game.get('possession')
            home_id = game.get('home_id')
            away_id = game.get('away_id')
            
            scoring_team = None
            if possession_id == home_id:
                scoring_team = game.get('home_abbr', '').upper()
            elif possession_id == away_id:
                scoring_team = game.get('away_abbr', '').upper()
            
            if not scoring_team:
                continue
            
            # Only alert for favorite teams
            if scoring_team not in [t.upper() for t in self.favorite_teams]:
                continue
            
            # Trigger the animation
            self.logger.info(f"SCORING ALERT: {scoring_team} - {scoring_event}")
            self._trigger_scoring_animation(scoring_team, scoring_event)
    
    def _trigger_scoring_animation(self, team: str, scoring_event: str):
        """Trigger the appropriate scoring animation."""
        primary, secondary = NFL_TEAM_COLORS.get(team, ((255, 255, 255), (255, 0, 0)))
        
        if scoring_event == "TOUCHDOWN":
            self._fancy_animation("TOUCHDOWN!!!", primary, secondary)
            trigger_wled_effect(effect_id=50, intensity=200, palette=3)
        elif scoring_event == "FIELD GOAL":
            self._fancy_animation("FIELD GOAL!", primary, secondary)
            trigger_wled_effect(effect_id=73, intensity=200, palette=3)
        elif scoring_event == "PAT":
            self._basic_animation("Extra Point", secondary)
            trigger_wled_effect(effect_id=73, intensity=200, palette=3)
    
    def _fancy_animation(self, message: str, primary_color: tuple, secondary_color: tuple):
        """Fancy animation for touchdowns and field goals."""
        matrix = self.display_manager.matrix
        
        # Flash screen (3 times)
        for _ in range(3):
            matrix.Fill(*primary_color)
            time.sleep(0.3)
            matrix.Clear()
            time.sleep(0.3)
        
        # Scroll text
        self._scroll_text_animation(message, secondary_color, speed=0.03)
        
        # Border chase (2 cycles)
        for _ in range(2):
            for color in [primary_color, secondary_color]:
                self._draw_border(color)
                time.sleep(0.2)
        
        # Confetti (3 seconds)
        for _ in range(30):
            matrix.Clear()
            for _ in range(20):
                x = random.randint(0, matrix.width - 1)
                y = random.randint(0, matrix.height - 1)
                matrix.SetPixel(x, y,
                    random.randint(50, 255),
                    random.randint(50, 255),
                    random.randint(50, 255))
            time.sleep(0.1)
        
        matrix.Clear()
    
    def _basic_animation(self, message: str, text_color: tuple):
        """Basic animation for extra points."""
        self._scroll_text_animation(message, text_color, speed=0.04)
    
    def _scroll_text_animation(self, text: str, color: tuple, speed: float = 0.05):
        """Scroll text across the display."""
        matrix = self.display_manager.matrix
        
        # Create image for text
        img_width = matrix.width * 3
        img = Image.new('RGB', (img_width, matrix.height), color=(0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Draw text
        text_y = matrix.height // 2 - 6
        draw.text((matrix.width, text_y), text, font=self.alert_font, fill=color)
        
        # Calculate scroll distance
        text_bbox = draw.textbbox((0, 0), text, font=self.alert_font)
        text_width = text_bbox[2] - text_bbox[0]
        total_scroll = int(matrix.width + text_width + matrix.width)
        
        # Scroll the text
        for x_offset in range(0, total_scroll, 2):
            display_img = img.crop((x_offset, 0, x_offset + matrix.width, matrix.height))
            matrix.SetImage(display_img.convert('RGB'), 0, 0)
            time.sleep(speed)
        
        matrix.Clear()
    
    def _draw_border(self, color: tuple):
        """Draw a border around the display."""
        matrix = self.display_manager.matrix
        width = matrix.width
        height = matrix.height
        
        # Top and bottom
        for x in range(width):
            matrix.SetPixel(x, 0, *color)
            matrix.SetPixel(x, height - 1, *color)
        
        # Left and right
        for y in range(height):
            matrix.SetPixel(0, y, *color)
            matrix.SetPixel(width - 1, y, *color)

    def update(self):
        """Update live game data and handle game switching."""
        if not self.is_enabled:
            return

        # Define current_time and interval before the problematic line (originally line 455)
        # Ensure 'import time' is present at the top of the file.
        current_time = time.time()

        # Define interval using a pattern similar to NFLLiveManager's update method.
        # Uses getattr for robustness, assuming attributes for live_games, test_mode,
        # no_data_interval, and update_interval are available on self.
        _live_games_attr = getattr(self, 'live_games', [])
        _test_mode_attr = getattr(self, 'test_mode', False) # test_mode is often from a base class or config
        _no_data_interval_attr = getattr(self, 'no_data_interval', 300) # Default similar to NFLLiveManager
        _update_interval_attr = getattr(self, 'update_interval', 15)   # Default similar to NFLLiveManager

        interval = _no_data_interval_attr if not _live_games_attr and not _test_mode_attr else _update_interval_attr
        
        # Original line from traceback (line 455), now with variables defined:
        if current_time - self.last_update >= interval:
            self.last_update = current_time

            # Fetch rankings if enabled
            if self.show_ranking:
                self._fetch_team_rankings()

            if self.test_mode:
                # Simulate clock running down in test mode
                if self.current_game and self.current_game["is_live"]:
                    try:
                        minutes, seconds = map(int, self.current_game["clock"].split(':'))
                        seconds -= 1
                        if seconds < 0:
                            seconds = 59
                            minutes -= 1
                            if minutes < 0:
                                # Simulate end of quarter/game
                                if self.current_game["period"] < 4: # Q4 is period 4
                                    self.current_game["period"] += 1
                                    # Update period_text based on new period
                                    if self.current_game["period"] == 1: self.current_game["period_text"] = "Q1"
                                    elif self.current_game["period"] == 2: self.current_game["period_text"] = "Q2"
                                    elif self.current_game["period"] == 3: self.current_game["period_text"] = "Q3"
                                    elif self.current_game["period"] == 4: self.current_game["period_text"] = "Q4"
                                    # Reset clock for next quarter (e.g., 15:00)
                                    minutes, seconds = 15, 0
                                else:
                                    # Simulate game end
                                    self.current_game["is_live"] = False
                                    self.current_game["is_final"] = True
                                    self.current_game["period_text"] = "Final"
                                    minutes, seconds = 0, 0
                        self.current_game["clock"] = f"{minutes:02d}:{seconds:02d}"
                        # Simulate down change occasionally
                        if seconds % 15 == 0:
                             self.current_game["down_distance_text"] = f"{['1st','2nd','3rd','4th'][seconds % 4]} & {seconds % 10 + 1}"
                        self.current_game["status_text"] = f"{self.current_game['period_text']} {self.current_game['clock']}"

                        # Display update handled by main loop or explicit call if needed immediately
                        # self.display(force_clear=True) # Only if immediate update is desired here

                    except ValueError:
                        self.logger.warning("Test mode: Could not parse clock") # Changed log prefix
                # No actual display call here, let main loop handle it
            else:
                # Fetch live game data
                data = self._fetch_data()
                new_live_games = []
                if data and "events" in data:
                    for game in data["events"]:
                        details = self._extract_game_details(game)
                        if details and (details["is_live"] or details["is_halftime"]):
                            # If show_favorite_teams_only is true, only add if it's a favorite.
                            # Otherwise, add all games.
                            if self.show_favorite_teams_only:
                                if details["home_abbr"] in self.favorite_teams or details["away_abbr"] in self.favorite_teams:
                                    new_live_games.append(details)
                            else:
                                new_live_games.append(details)
                    for game in new_live_games:
                        if self.show_odds:
                            self._fetch_odds(game)
                    # Log changes or periodically
                    current_time_for_log = time.time() # Use a consistent time for logging comparison
                    should_log = (
                        current_time_for_log - self.last_log_time >= self.log_interval or
                        len(new_live_games) != len(self.live_games) or
                        any(g1['id'] != g2.get('id') for g1, g2 in zip(self.live_games, new_live_games)) or # Check if game IDs changed
                        (not self.live_games and new_live_games) # Log if games appeared
                    )

                    if should_log:
                        if new_live_games:
                            filter_text = "favorite teams" if self.show_favorite_teams_only else "all teams"
                            self.logger.info(f"Found {len(new_live_games)} live/halftime games for {filter_text}.")
                            for game_info in new_live_games: # Renamed game to game_info
                                self.logger.info(f"  - {game_info['away_abbr']}@{game_info['home_abbr']} ({game_info.get('status_text', 'N/A')})")
                        else:
                            filter_text = "favorite teams" if self.show_favorite_teams_only else "criteria"
                            self.logger.info(f"No live/halftime games found for {filter_text}.")
                        self.last_log_time = current_time_for_log


                    # Update game list and current game
                    if new_live_games:
                        # Check if the games themselves changed, not just scores/time
                        new_game_ids = {g['id'] for g in new_live_games}
                        current_game_ids = {g['id'] for g in self.live_games}

                        if new_game_ids != current_game_ids:
                            self.live_games = sorted(new_live_games, key=lambda g: g.get('start_time_utc') or datetime.now(timezone.utc)) # Sort by start time
                            # Reset index if current game is gone or list is new
                            if not self.current_game or self.current_game['id'] not in new_game_ids:
                                self.current_game_index = 0
                                self.current_game = self.live_games[0] if self.live_games else None
                                self.last_game_switch = current_time
                            else:
                                # Find current game's new index if it still exists
                                try:
                                     self.current_game_index = next(i for i, g in enumerate(self.live_games) if g['id'] == self.current_game['id'])
                                     self.current_game = self.live_games[self.current_game_index] # Update current_game with fresh data
                                except StopIteration: # Should not happen if check above passed, but safety first
                                     self.current_game_index = 0
                                     self.current_game = self.live_games[0]
                                     self.last_game_switch = current_time

                        else:
                             # Just update the data for the existing games
                             temp_game_dict = {g['id']: g for g in new_live_games}
                             self.live_games = [temp_game_dict.get(g['id'], g) for g in self.live_games] # Update in place
                             if self.current_game:
                                  self.current_game = temp_game_dict.get(self.current_game['id'], self.current_game)

                        # CHECK FOR SCORING EVENTS - NEW LINE ADDED HERE
                        self._check_scoring_events()

                    else:
                        # No live games found
                        if self.live_games: # Were there games before?
                            self.logger.info("Live games previously showing have ended or are no longer live.") # Changed log prefix
                        self.live_games = []
                        self.current_game = None
                        self.current_game_index = 0

                else:
                    # Error fetching data or no events
                     if self.live_games: # Were there games before?
                         self.logger.warning("Could not fetch update; keeping existing live game data for now.") # Changed log prefix
                     else:
                         self.logger.warning("Could not fetch data and no existing live games.") # Changed log prefix
                         self.current_game = None # Clear current game if fetch fails and no games were active

            # Handle game switching (outside test mode check)
            if not self.test_mode and len(self.live_games) > 1 and (current_time - self.last_game_switch) >= self.game_display_duration:
                self.current_game_index = (self.current_game_index + 1) % len(self.live_games)
                self.current_game = self.live_games[self.current_game_index]
                self.last_game_switch = current_time
                self.logger.info(f"Switched live view to: {self.current_game['away_abbr']}@{self.current_game['home_abbr']}") # Changed log prefix
                # Force display update via flag or direct call if needed, but usually let main loop handle

    def trigger_wled_effect(effect_id: int = 1, intensity: int = 128, palette: int = 0):
        try:
            WLED_IP = "http://10.0.0.116/"  # <-- replace with your WLED controller's IP
            url = f"http://{WLED_IP}/json/state"
            payload = {
                "on": True,
                "bri": 255,
                "seg": [{
                    "fx": effect_id,     # effect number
                    "sx": intensity,     # speed (0–255)
                    "ix": 128,           # intensity (0–255)
                    "pal": palette       # palette number
                }]
            }
            requests.post(url, json=payload, timeout=2)
        except Exception as e:
            logging.error(f"Failed to trigger WLED effect: {e}")


    def _draw_scorebug_layout(self, game: Dict, force_clear: bool = False) -> None:
        """Draw the detailed scorebug layout for a live NCAA FB game.""" # Updated docstring
        try:
            main_img = Image.new('RGBA', (self.display_width, self.display_height), (0, 0, 0, 255))
            overlay = Image.new('RGBA', (self.display_width, self.display_height), (0, 0, 0, 0))
            draw_overlay = ImageDraw.Draw(overlay) # Draw text elements on overlay first

            home_logo = self._load_and_resize_logo(game["home_id"], game["home_abbr"], game["home_logo_path"], game.get("home_logo_url"))
            away_logo = self._load_and_resize_logo(game["away_id"], game["away_abbr"], game["away_logo_path"], game.get("away_logo_url"))

            if not home_logo or not away_logo:
                self.logger.error(f"Failed to load logos for live game: {game.get('id')}") # Changed log prefix
                # Draw placeholder text if logos fail
                draw_final = ImageDraw.Draw(main_img.convert('RGB'))
                self._draw_text_with_outline(draw_final, "Logo Error", (5,5), self.fonts['status'])
                self.display_manager.image.paste(main_img.convert('RGB'), (0, 0))
                self.display_manager.update_display()
                return

            center_y = self.display_height // 2

            # Draw logos (shifted slightly more inward than NHL perhaps)
            home_x = self.display_width - home_logo.width + 10 #adjusted from 18 # Adjust position as needed
            home_y = center_y - (home_logo.height // 2)
            main_img.paste(home_logo, (home_x, home_y), home_logo)

            away_x = -10 #adjusted from 18 # Adjust position as needed
            away_y = center_y - (away_logo.height // 2)
            main_img.paste(away_logo, (away_x, away_y), away_logo)

            # --- Draw Text Elements on Overlay ---
            # Note: Rankings are now handled in the records/rankings section below

            # Scores (centered, slightly above bottom)
            home_score = str(game.get("home_score", "0"))
            away_score = str(game.get("away_score", "0"))
            score_text = f"{away_score}-{home_score}"
            score_width = draw_overlay.textlength(score_text, font=self.fonts['score'])
            score_x = (self.display_width - score_width) // 2
            score_y = (self.display_height // 2) - 3 #centered #from 14 # Position score higher
            self._draw_text_with_outline(draw_overlay, score_text, (score_x, score_y), self.fonts['score'])

            # Period/Quarter and Clock (Top center)
            period_clock_text = f"{game.get('period_text', '')} {game.get('clock', '')}".strip()
            if game.get("is_halftime"): period_clock_text = "Halftime" # Override for halftime

            status_width = draw_overlay.textlength(period_clock_text, font=self.fonts['time'])
            status_x = (self.display_width - status_width) // 2
            status_y = 1 # Position at top
            self._draw_text_with_outline(draw_overlay, period_clock_text, (status_x, status_y), self.fonts['time'])

            # Down & Distance or Scoring Event (Below Period/Clock)
            scoring_event = game.get("scoring_event", "")
            down_distance = game.get("down_distance_text", "")
            
            # Show scoring event if detected, otherwise show down & distance
            if scoring_event and game.get("is_live"):
                # Display scoring event with special formatting
                event_width = draw_overlay.textlength(scoring_event, font=self.fonts['detail'])
                event_x = (self.display_width - event_width) // 2
                event_y = (self.display_height) - 7
                
                # Color coding for different scoring events
                if scoring_event == "TOUCHDOWN":
                    event_color = (255, 215, 0)  # Gold
                elif scoring_event == "FIELD GOAL":
                    event_color = (0, 255, 0)    # Green
                elif scoring_event == "PAT":
                    event_color = (255, 165, 0)  # Orange
                else:
                    event_color = (255, 255, 255)  # White
                
                self._draw_text_with_outline(draw_overlay, scoring_event, (event_x, event_y), self.fonts['detail'], fill=event_color)
            elif down_distance and game.get("is_live"): # Only show if live and available
                dd_width = draw_overlay.textlength(down_distance, font=self.fonts['detail'])
                dd_x = (self.display_width - dd_width) // 2
                dd_y = (self.display_height)- 7 # Top of D&D text
                down_color = (200, 200, 0) if not game.get("is_redzone", False) else (255,0,0) # Yellowish text
                self._draw_text_with_outline(draw_overlay, down_distance, (dd_x, dd_y), self.fonts['detail'], fill=down_color)

                # Possession Indicator (small football icon)
                possession = game.get("possession_indicator")
                if possession: # Only draw if possession is known
                    ball_radius_x = 3  # Wider for football shape
                    ball_radius_y = 2  # Shorter for football shape
                    ball_color = (139, 69, 19) # Brown color for the football
                    lace_color = (255, 255, 255) # White for laces

                    # Approximate height of the detail font (4x6 font at size 6 is roughly 6px tall)
                    detail_font_height_approx = 6
                    ball_y_center = dd_y + (detail_font_height_approx // 2) # Center ball vertically with D&D text

                    possession_ball_padding = 3 # Pixels between D&D text and ball

                    if possession == "away":
                        # Position ball to the left of D&D text
                        ball_x_center = dd_x - possession_ball_padding - ball_radius_x
                    elif possession == "home":
                        # Position ball to the right of D&D text
                        ball_x_center = dd_x + dd_width + possession_ball_padding + ball_radius_x
                    else:
                        ball_x_center = 0 # Should not happen / no indicator

                    if ball_x_center > 0: # Draw if position is valid
                        # Draw the football shape (ellipse)
                        draw_overlay.ellipse(
                            (ball_x_center - ball_radius_x, ball_y_center - ball_radius_y,  # x0, y0
                             ball_x_center + ball_radius_x, ball_y_center + ball_radius_y), # x1, y1
                            fill=ball_color, outline=(0,0,0)
                        )
                        # Draw a simple horizontal lace
                        draw_overlay.line(
                            (ball_x_center - 1, ball_y_center, ball_x_center + 1, ball_y_center),
                            fill=lace_color, width=1
                        )

            # Timeouts (Bottom corners) - 3 small bars per team
            timeout_bar_width = 4
            timeout_bar_height = 2
            timeout_spacing = 1
            timeout_y = self.display_height - timeout_bar_height - 1 # Bottom edge

            # Away Timeouts (Bottom Left)
            away_timeouts_remaining = game.get("away_timeouts", 0)
            for i in range(3):
                to_x = 2 + i * (timeout_bar_width + timeout_spacing)
                color = (255, 255, 255) if i < away_timeouts_remaining else (80, 80, 80) # White if available, gray if used
                draw_overlay.rectangle([to_x, timeout_y, to_x + timeout_bar_width, timeout_y + timeout_bar_height], fill=color, outline=(0,0,0))

             # Home Timeouts (Bottom Right)
            home_timeouts_remaining = game.get("home_timeouts", 0)
            for i in range(3):
                to_x = self.display_width - 2 - timeout_bar_width - (2-i) * (timeout_bar_width + timeout_spacing)
                color = (255, 255, 255) if i < home_timeouts_remaining else (80, 80, 80) # White if available, gray if used
                draw_overlay.rectangle([to_x, timeout_y, to_x + timeout_bar_width, timeout_y + timeout_bar_height], fill=color, outline=(0,0,0))

            # Draw odds if available
            if 'odds' in game and game['odds']:
                self._draw_dynamic_odds(draw_overlay, game['odds'], self.display_width, self.display_height)

            # Draw records or rankings if enabled
            if self.show_records or self.show_ranking:
                try:
                    record_font = ImageFont.truetype("assets/fonts/4x6-font.ttf", 6)
                    self.logger.debug(f"Loaded 6px record font successfully")
                except IOError:
                    record_font = ImageFont.load_default()
                    self.logger.warning(f"Failed to load 6px font, using default font (size: {record_font.size})")
                
                # Get team abbreviations
                away_abbr = game.get('away_abbr', '')
                home_abbr = game.get('home_abbr', '')
                
                record_bbox = draw_overlay.textbbox((0,0), "0-0", font=record_font)
                record_height = record_bbox[3] - record_bbox[1]
                record_y = self.display_height - record_height - 4
                self.logger.debug(f"Record positioning: height={record_height}, record_y={record_y}, display_height={self.display_height}")

                # Display away team info
                if away_abbr:
                    if self.show_ranking and self.show_records:
                        # When both rankings and records are enabled, rankings replace records completely
                        away_rank = self._team_rankings_cache.get(away_abbr, 0)
                        if away_rank > 0:
                            away_text = f"#{away_rank}"
                        else:
                            # Show nothing for unranked teams when rankings are prioritized
                            away_text = ''
                    elif self.show_ranking:
                        # Show ranking only if available
                        away_rank = self._team_rankings_cache.get(away_abbr, 0)
                        if away_rank > 0:
                            away_text = f"#{away_rank}"
                        else:
                            away_text = ''
                    elif self.show_records:
                        # Show record only when rankings are disabled
                        away_text = game.get('away_record', '')
                    else:
                        away_text = ''
                    
                    if away_text:
                        away_record_x = 3
                        self.logger.debug(f"Drawing away ranking '{away_text}' at ({away_record_x}, {record_y}) with font size {record_font.size if hasattr(record_font, 'size') else 'unknown'}")
                        self._draw_text_with_outline(draw_overlay, away_text, (away_record_x, record_y), record_font)

                # Display home team info
                if home_abbr:
                    if self.show_ranking and self.show_records:
                        # When both rankings and records are enabled, rankings replace records completely
                        home_rank = self._team_rankings_cache.get(home_abbr, 0)
                        if home_rank > 0:
                            home_text = f"#{home_rank}"
                        else:
                            # Show nothing for unranked teams when rankings are prioritized
                            home_text = ''
                    elif self.show_ranking:
                        # Show ranking only if available
                        home_rank = self._team_rankings_cache.get(home_abbr, 0)
                        if home_rank > 0:
                            home_text = f"#{home_rank}"
                        else:
                            home_text = ''
                    elif self.show_records:
                        # Show record only when rankings are disabled
                        home_text = game.get('home_record', '')
                    else:
                        home_text = ''
                    
                    if home_text:
                        home_record_bbox = draw_overlay.textbbox((0,0), home_text, font=record_font)
                        home_record_width = home_record_bbox[2] - home_record_bbox[0]
                        home_record_x = self.display_width - home_record_width - 3
                        self.logger.debug(f"Drawing home ranking '{home_text}' at ({home_record_x}, {record_y}) with font size {record_font.size if hasattr(record_font, 'size') else 'unknown'}")
                        self._draw_text_with_outline(draw_overlay, home_text, (home_record_x, record_y), record_font)

            # Composite the text overlay onto the main image
            main_img = Image.alpha_composite(main_img, overlay)
            main_img = main_img.convert('RGB') # Convert for display

            # Display the final image
            self.display_manager.image.paste(main_img, (0, 0))
            self.display_manager.update_display() # Update display here for live

        except Exception as e:
            self.logger.error(f"Error displaying live Football game: {e}", exc_info=True) # Changed log prefix

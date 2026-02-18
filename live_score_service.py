#!/usr/bin/env python
"""
MODULAR LIVE SCORE SERVICE - Real-time game updates
Uses official APIs (NBA, ESPN site API) instead of stale HTML scraping
Can swap sources without changing main logic
"""

import requests
import json
import time
from datetime import datetime
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict


@dataclass
class GameScore:
    """Standard game score object"""
    game_id: str
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    status: str  # "Live", "Halftime", "Final", "Scheduled"
    sport: str  # "NBA", "NCAAB", "NFL"
    last_update: str  # ISO timestamp
    spread: float = 0.0  # For tracking


class ScoreSource(ABC):
    """Base class for swappable score sources"""
    
    @abstractmethod
    def fetch_games(self) -> List[GameScore]:
        """Fetch live games"""
        pass
    
    @abstractmethod
    def sport(self) -> str:
        """Return sport code"""
        pass


class NBAOfficialSource(ScoreSource):
    """NBA Official API - Real-time live scores"""
    
    def __init__(self):
        self.headers = {"User-Agent": "Mozilla/5.0"}
        self.base_url = "https://cdn.nba.com/static/json/liveData/scoreboard"
    
    def sport(self) -> str:
        return "NBA"
    
    def fetch_games(self) -> List[GameScore]:
        games = []
        try:
            resp = requests.get(
                f"{self.base_url}/todaysScoreboard_00.json",
                headers=self.headers,
                timeout=10
            )
            
            if resp.status_code != 200:
                print(f"  NBA API error: {resp.status_code}")
                return games
            
            data = resp.json()
            
            for game in data.get('scoreboard', {}).get('games', []):
                home = game.get('homeTeam', {})
                away = game.get('awayTeam', {})
                
                # Map game status
                status_num = game.get('gameStatus', 0)
                status_map = {
                    0: "Scheduled",
                    1: "In Progress",
                    2: "Final",
                    3: "OT",
                }
                status = status_map.get(status_num, "Unknown")
                
                # Check if halftime
                period = game.get('period', 0)
                if status == "In Progress" and game.get('gameClock') == "0:00" and period == 2:
                    status = "Halftime"
                
                games.append(GameScore(
                    game_id=game.get('gameId', ''),
                    home_team=home.get('teamName', 'Unknown'),
                    away_team=away.get('teamName', 'Unknown'),
                    home_score=home.get('score', 0),
                    away_score=away.get('score', 0),
                    status=status,
                    sport=self.sport(),
                    last_update=datetime.now().isoformat(timespec='seconds'),
                ))
        
        except Exception as e:
            print(f"  NBA fetch error: {e}")
        
        return games


class NCAABESPNSource(ScoreSource):
    """ESPN site API for NCAAB live scores"""
    
    def __init__(self):
        self.headers = {"User-Agent": "Mozilla/5.0"}
        self.base_url = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball"
    
    def sport(self) -> str:
        return "NCAAB"
    
    def fetch_games(self) -> List[GameScore]:
        games = []
        try:
            resp = requests.get(
                f"{self.base_url}/scoreboard",
                headers=self.headers,
                timeout=10
            )
            
            if resp.status_code != 200:
                print(f"  NCAAB API error: {resp.status_code}")
                return games
            
            data = resp.json()
            
            for event in data.get('events', []):
                competitions = event.get('competitions', [])
                if not competitions:
                    continue
                comps = competitions[0]
                competitors = comps.get('competitors', [])
                
                if len(competitors) < 2:
                    continue
                
                # Determine home/away
                home = competitors[0]
                away = competitors[1]
                
                # Status
                status_obj = comps.get('status', {})
                # status_obj['type'] is a dict with 'description' key
                if isinstance(status_obj.get('type'), dict):
                    status = status_obj['type'].get('description', 'Unknown')
                else:
                    # Fallback: might be a string
                    status_str = status_obj.get('type', 'pre')
                    status_map = {
                        'pre': 'Scheduled',
                        'in': 'Live',
                        'post': 'Final',
                    }
                    status = status_map.get(status_str, 'Unknown')
                
                games.append(GameScore(
                    game_id=event.get('id', ''),
                    home_team=home.get('team', {}).get('displayName', 'Unknown'),
                    away_team=away.get('team', {}).get('displayName', 'Unknown'),
                    home_score=int(home.get('score', 0)),
                    away_score=int(away.get('score', 0)),
                    status=status,
                    sport=self.sport(),
                    last_update=datetime.now().isoformat(timespec='seconds'),
                ))
        
        except Exception as e:
            print(f"  NCAAB fetch error: {e}")
        
        return games


class NFLESPNSource(ScoreSource):
    """ESPN site API for NFL live scores"""
    
    def __init__(self):
        self.headers = {"User-Agent": "Mozilla/5.0"}
        self.base_url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
    
    def sport(self) -> str:
        return "NFL"
    
    def fetch_games(self) -> List[GameScore]:
        games = []
        try:
            resp = requests.get(
                f"{self.base_url}/scoreboard",
                headers=self.headers,
                timeout=10
            )
            
            if resp.status_code != 200:
                return games
            
            data = resp.json()
            
            for event in data.get('events', []):
                competitions = event.get('competitions', [])
                if not competitions:
                    continue
                comps = competitions[0]
                competitors = comps.get('competitors', [])
                
                if len(competitors) < 2:
                    continue
                
                home = competitors[0]
                away = competitors[1]
                
                status_obj = comps.get('status', {})
                if isinstance(status_obj.get('type'), dict):
                    status = status_obj['type'].get('description', 'Unknown')
                else:
                    status_str = status_obj.get('type', 'pre')
                    status_map = {'pre': 'Scheduled', 'in': 'Live', 'post': 'Final'}
                    status = status_map.get(status_str, 'Unknown')
                
                games.append(GameScore(
                    game_id=event.get('id', ''),
                    home_team=home.get('team', {}).get('displayName', 'Unknown'),
                    away_team=away.get('team', {}).get('displayName', 'Unknown'),
                    home_score=int(home.get('score', 0)),
                    away_score=int(away.get('score', 0)),
                    status=status,
                    sport=self.sport(),
                    last_update=datetime.now().isoformat(timespec='seconds'),
                ))
        
        except Exception as e:
            print(f"  NFL fetch error: {e}")
        
        return games


class NCAAWESPNSource(ScoreSource):
    """ESPN site API for NCAAW (Women's College Basketball) live scores"""
    
    def __init__(self):
        self.headers = {"User-Agent": "Mozilla/5.0"}
        self.base_url = "https://site.api.espn.com/apis/site/v2/sports/basketball/womens-college-basketball"
    
    def sport(self) -> str:
        return "NCAAW"
    
    def fetch_games(self) -> List[GameScore]:
        games = []
        try:
            resp = requests.get(
                f"{self.base_url}/scoreboard",
                headers=self.headers,
                timeout=10
            )
            
            if resp.status_code != 200:
                print(f"  NCAAW API error: {resp.status_code}")
                return games
            
            data = resp.json()
            
            for event in data.get('events', []):
                competitions = event.get('competitions', [])
                if not competitions:
                    continue
                comps = competitions[0]
                competitors = comps.get('competitors', [])
                
                if len(competitors) < 2:
                    continue
                
                # Determine home/away
                home = competitors[0]
                away = competitors[1]
                
                # Status
                status_obj = comps.get('status', {})
                # status_obj['type'] is a dict with 'description' key
                if isinstance(status_obj.get('type'), dict):
                    status = status_obj['type'].get('description', 'Unknown')
                else:
                    # Fallback: might be a string
                    status_str = status_obj.get('type', 'pre')
                    status_map = {
                        'pre': 'Scheduled',
                        'in': 'Live',
                        'post': 'Final',
                    }
                    status = status_map.get(status_str, 'Unknown')
                
                games.append(GameScore(
                    game_id=event.get('id', ''),
                    home_team=home.get('team', {}).get('displayName', 'Unknown'),
                    away_team=away.get('team', {}).get('displayName', 'Unknown'),
                    home_score=int(home.get('score', 0)),
                    away_score=int(away.get('score', 0)),
                    status=status,
                    sport=self.sport(),
                    last_update=datetime.now().isoformat(timespec='seconds'),
                ))
        
        except Exception as e:
            print(f"  NCAAW fetch error: {e}")
        
        return games


class LiveScoreService:
    """Main service - coordinates multiple sources"""
    
    def __init__(self):
        self.sources: Dict[str, ScoreSource] = {
            'nba': NBAOfficialSource(),
            'ncaab': NCAABESPNSource(),
            'ncaaw': NCAAWESPNSource(),
            'nfl': NFLESPNSource(),
        }
        self.last_state = {}
    
    def fetch_all_games(self) -> Dict[str, List[GameScore]]:
        """Fetch games from all sources"""
        all_games = {}
        
        for source_name, source in self.sources.items():
            games = source.fetch_games()
            if games:
                all_games[source_name] = games
        
        return all_games
    
    def stream(self, duration_seconds=180, interval_seconds=10):
        """Stream live scores continuously"""
        
        print("\n" + "="*80)
        print(f"LIVE SCORE SERVICE - Real-time updates")
        print(f"Polling every {interval_seconds}s, max {duration_seconds}s")
        print("="*80 + "\n")
        
        start = time.time()
        poll_num = 0
        
        try:
            while time.time() - start < duration_seconds:
                poll_num += 1
                now = datetime.now().strftime("%H:%M:%S")
                
                all_games = self.fetch_all_games()
                
                # Check if anything changed
                has_changes = str(all_games) != str(self.last_state)
                
                if has_changes or poll_num == 1:
                    print(f"\n[{now}] Poll #{poll_num} - LIVE SCORES")
                    print("-" * 80)
                    
                    for sport, games in sorted(all_games.items()):
                        if games:
                            print(f"\n  [{sport.upper()}] - {len(games)} games")
                            
                            for game in games:
                                # Only show live/halftime games
                                if game.status in ['Live', 'Halftime', 'Final']:
                                    margin = game.home_score - game.away_score
                                    print(f"    {game.away_team} {game.away_score:3d} @ {game.home_team} {game.home_score:3d}  ({game.status:8s}) margin: {margin:+3d}")
                    
                    self.last_state = dict(all_games)
                
                else:
                    print(f"[{now}] Poll #{poll_num} - No changes")
                
                time.sleep(interval_seconds)
        
        except KeyboardInterrupt:
            print(f"\n\nStopped after {poll_num} polls")
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
        
        print("\n" + "="*80)


def main():
    service = LiveScoreService()
    service.stream(duration_seconds=240, interval_seconds=15)


if __name__ == "__main__":
    main()

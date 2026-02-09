"""
Parser for whale bet alerts from social media

Handles formats like:
- "A bettor placed $165,000 on Alabama +3 vs. Georgia (-110)"
- "BIG BET ALERT: $35,000 on ARI Cardinals ML (+102)"
- "$50K bet: Lakers -7.5 vs Warriors"
"""

import re
from typing import Optional, Dict, Any
from loguru import logger


class WhaleAlertParser:
    """Parse whale bet alerts from text"""
    
    # Regex patterns
    AMOUNT_PATTERN = r'\$(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)[kK]?'
    TEAM_PATTERN = r'(?:on\s+)([A-Z][A-Za-z\s]+?)(?:\s+(?:ML|moneyline|\+|-|\d))'
    ODDS_PATTERN = r'([+-]\d+)'
    SPREAD_PATTERN = r'([+-]?\d+\.?\d*)'
    
    def parse_whale_alert(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Parse whale bet alert from text
        
        Args:
            text: Alert text to parse
            
        Returns:
            Parsed whale bet data or None if invalid
        """
        try:
            # Extract amount
            amount = self.extract_amount(text)
            if not amount or amount < 1000:  # Minimum $1K to be considered
                return None
            
            # Extract team/selection
            selection = self.extract_selection(text)
            if not selection:
                return None
            
            # Extract odds
            odds = self.extract_odds(text)
            
            # Determine bet type
            bet_type = self.determine_bet_type(text, selection)
            
            # Calculate potential payout
            payout = self.calculate_payout(amount, odds) if odds else None
            
            return {
                "amount": amount,
                "selection": selection,
                "odds": odds,
                "bet_type": bet_type,
                "potential_payout": payout,
                "raw_text": text
            }
            
        except Exception as e:
            logger.error(f"Error parsing whale alert: {e}")
            return None
    
    def extract_amount(self, text: str) -> Optional[float]:
        """
        Extract bet amount from text
        
        Args:
            text: Text to parse
            
        Returns:
            Bet amount in dollars
        """
        match = re.search(self.AMOUNT_PATTERN, text, re.IGNORECASE)
        if not match:
            return None
        
        amount_str = match.group(1).replace(",", "")
        amount = float(amount_str)
        
        # Check for "K" suffix (thousands)
        if 'k' in match.group(0).lower():
            amount *= 1000
        
        return amount
    
    def extract_selection(self, text: str) -> Optional[str]:
        """
        Extract team/player selection from text
        
        Args:
            text: Text to parse
            
        Returns:
            Selection string
        """
        # Try different patterns
        patterns = [
            r'on\s+([A-Z][A-Za-z\s]+?)(?:\s+(?:ML|moneyline|to\s+win|\+|-|\d))',
            r'([A-Z][A-Za-z\s]+?)\s+(?:ML|moneyline)',
            r'([A-Z][A-Za-z\s]+?)\s+([+-]\d+\.?\d*)',
            r'([A-Z][A-Za-z\s]+?)\s+vs'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                team = match.group(1).strip()
                # Clean up common suffixes
                team = re.sub(r'\s+(bet|wager|at|to)$', '', team, flags=re.IGNORECASE)
                return team
        
        return None
    
    def extract_odds(self, text: str) -> Optional[int]:
        """
        Extract American odds from text
        
        Args:
            text: Text to parse
            
        Returns:
            American odds (e.g., +110, -150)
        """
        match = re.search(r'\(([+-]\d+)\)', text)
        if match:
            return int(match.group(1))
        
        match = re.search(r'([+-]\d+)', text)
        if match:
            return int(match.group(1))
        
        return None
    
    def determine_bet_type(self, text: str, selection: str) -> str:
        """
        Determine bet type from text
        
        Args:
            text: Text to analyze
            selection: Extracted selection
            
        Returns:
            Bet type string
        """
        text_lower = text.lower()
        
        if 'ml' in text_lower or 'moneyline' in text_lower:
            return "moneyline"
        elif 'over' in text_lower:
            return "totals"
        elif 'under' in text_lower:
            return "totals"
        elif re.search(r'[+-]\d+\.5', text):
            return "spread"
        else:
            return "moneyline"  # Default
    
    def calculate_payout(self, amount: float, odds: int) -> float:
        """
        Calculate potential payout from amount and odds
        
        Args:
            amount: Bet amount
            odds: American odds
            
        Returns:
            Potential payout (including original stake)
        """
        if odds > 0:
            # Positive odds: profit = (odds/100) * amount
            profit = (odds / 100) * amount
        else:
            # Negative odds: profit = (100/abs(odds)) * amount
            profit = (100 / abs(odds)) * amount
        
        return amount + profit
    
    def is_valid_whale_bet(
        self,
        amount: float,
        min_threshold: float = 10000
    ) -> bool:
        """
        Check if bet amount qualifies as a whale bet
        
        Args:
            amount: Bet amount
            min_threshold: Minimum amount to qualify
            
        Returns:
            True if whale bet
        """
        return amount >= min_threshold


# Example usage and tests
if __name__ == "__main__":
    parser = WhaleAlertParser()
    
    test_alerts = [
        "A bettor placed $165,000 on Alabama +3 vs. Georgia (-110)",
        "BIG BET ALERT: $35,000 on ARI Cardinals ML (+102)",
        "$50K bet: Lakers -7.5 vs Warriors",
        "Someone just dropped $100,000 on Over 45.5 (-110)",
    ]
    
    for alert in test_alerts:
        print(f"\nParsing: {alert}")
        result = parser.parse_whale_alert(alert)
        if result:
            print(f"Amount: ${result['amount']:,.0f}")
            print(f"Selection: {result['selection']}")
            print(f"Odds: {result['odds']}")
            print(f"Type: {result['bet_type']}")
            if result['potential_payout']:
                print(f"Payout: ${result['potential_payout']:,.0f}")

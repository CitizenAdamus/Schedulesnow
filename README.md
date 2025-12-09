# Driver Schedule Builder – Toronto Winter Edition 2025

Smart greedy scheduler that builds optimal driver routes in seconds.  
Used daily by dispatch at [Your Company Name] to turn 200–400 loose trips into clean, road-legal, winter-ready driver schedules.

### Key Features
- 120 km hard cap per driver
- 12-hour maximum shift (first pickup → last drop)
- Zone-based connection rules with configurable gaps
- Special **Snow Mode** with longer randomized gaps for northern zones during bad weather
- Full audit trail: every trip linkage is justified in plain English
- One-click CSV + Excel export

### Winter / Snow Mode (2025 Update)
When enabled, any trip touching these zones automatically gets longer gaps:

**Snow Zones**: 1, 2, 3, 4, 5, 6, 8, 10, 11, 13, 17, 30, 32, 34

| Zone Distance | Normal Gap | Snow Mode Gap (randomized) |
|---------------|------------|----------------------------|
| 0 (same zone) | 10 min     | 10–15 min                  |
| 1 (adjacent)  | 15 min     | 15–20 min                  |
| 2 (2-hop)     | 20 min     | 20–25 min                  |

All other zones keep normal gaps year-round.

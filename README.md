# Spaceship Coordination Experiment

A multiplayer, timed, coordination game for academic research built with oTree and Django Channels.

## Overview

This experiment simulates a mining spaceship operation where 3-person crews must coordinate to maximize mineral extraction while managing power units. The system supports a 2×2×2 experimental design manipulating:

- **Communication Pressure** (high/low): Briefing time constraints (90s vs 180s)
- **Information Complexity** (high/low): Private vs shared intel
- **Captain Type** (Human/LLM): Human coordination vs AI captain

## Features

- **Real-time multiplayer coordination** via WebSockets
- **AI Captain system** using AutoGen for LLM conditions
- **Comprehensive data logging** for research analysis
- **Admin controls** for experiment management
- **Prolific integration** for participant management
- **Responsive UI** with accessibility features

## Architecture

### Backend Stack
- **oTree 5.8.0**: Experiment framework and participant management
- **Django 4.2.7**: Web framework and ORM
- **Django Channels**: WebSocket support for real-time communication
- **PostgreSQL**: Primary database
- **Redis**: Channel layer backend for WebSockets

### Key Components
- **Game Engine**: Core game logic and state management
- **AI Captain**: LLM-based coordination system
- **WebSocket Consumers**: Real-time game updates
- **Admin Interface**: Experiment monitoring and control

## Installation

### Prerequisites
- Python 3.11+
- PostgreSQL 12+
- Redis 6+
- Node.js 16+ (for frontend assets)

### Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd AI-Coordination-Wireframe
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment configuration**
   Create a `.env` file in the project root:
   ```env
   DEBUG=True
   SECRET_KEY=your-secret-key-here
   DB_NAME=spaceship_coordination
   DB_USER=postgres
   DB_PASSWORD=your-db-password
   DB_HOST=localhost
   DB_PORT=5432
   REDIS_URL=redis://localhost:6379
   ```

5. **Database setup**
   ```bash
   # Create PostgreSQL database
   createdb spaceship_coordination
   
   # Run migrations
   python manage.py migrate
   ```

6. **Create superuser**
   ```bash
   python manage.py createsuperuser
   ```

7. **Start services**
   ```bash
   # Start Redis (in separate terminal)
   redis-server
   
   # Start Django development server
   python manage.py runserver
   ```

## 🆕 **New Features: Automatic Session Setup**

### **Automatic Setup**
- **New sessions automatically create** default asteroids and crew
- **Default asteroids**: Alpha, Beta, Gamma, Omega with balanced stats
- **Default crew**: Ready for participants to join

### **Admin Portal Actions**
- **Create Default Setup**: Manually create setup for existing sessions
- **Reset to Default**: Reset session to clean state
- **Session Overview**: See crew and asteroid counts at a glance

### **Management Commands**
```bash
# Create a test session with automatic setup
python manage.py create_test_session

# Create with custom parameters
python manage.py create_test_session --session-id "high_pressure_test" --pressure high --complexity low --captain-type human
```

## Game Mechanics

### Formal Implementation
The game mechanics are now fully implemented according to the formal specifications document, including:

- **Round Structure**: Briefing → Action → Result stages with proper timing
- **Action Validation**: Enforces all formal constraints (max probes, max robots, PU limits)
- **Mining Outcomes**: Probability-based system using formal probability matrix
- **Intel Visibility**: Proper implementation of high/low complexity conditions
- **State Transitions**: Follows formal execution order (Navigator effects precede Driller effects)

### Roles
- **Captain**: Coordinates during briefing, cannot take actions
- **Navigator**: Travels between asteroids, sends probes (max 2/round)
- **Driller**: Mines asteroids, deploys robots (max 1/round)

### Resources
- **Power Units (PU)**: Team budget per round (default: 4 PU)
- **Asteroids**: Alpha (start), Beta, Gamma, Omega
- **Travel Costs**: Alpha→Alpha (0), Beta (1), Gamma (2), Omega (3)

### Actions
- **Travel**: Move to different asteroid
- **Send Probe**: Reveal max minerals (1 PU)
- **Deploy Robot**: Reveal mining costs (1 PU)
- **Mine**: Extract minerals (Shallow: 1 PU, Deep: 2 PU)

### Mining Outcomes
Success probability depends on:
1. **Depth**: Shallow vs Deep
2. **Intel**: Probe + Robot combination
3. **Random factors** with configurable probability matrix

### Intel Visibility
- **High Complexity**: Intel remains private to discoverer
- **Low Complexity**: Intel automatically shared with all crew members
- **Probes**: Reveal maximum minerals available
- **Robots**: Reveal mining costs (shallow and deep)

## Experimental Design

### Conditions
- **High Pressure**: 90s briefing, 15s action, 15s result
- **Low Pressure**: 180s briefing, 15s action, 15s result
- **High Complexity**: Intel remains private to discoverer
- **Low Complexity**: Intel automatically shared with team
- **Human Captain**: 3 human participants
- **LLM Captain**: 2 humans + AI captain

### Randomization
- Balanced condition assignment using block randomization
- Random role assignment among human participants
- Seeded random generation for reproducible results

## Usage

### Running Experiments

1. **Access admin interface**
   - Navigate to `/admin/`
   - Login with superuser credentials

2. **Create experiment session**
   - Set pressure, complexity, and captain type
   - Configure probability matrices and costs

3. **Monitor participants**
   - View crew status and progress
   - Monitor real-time game state
   - Handle disconnections and timeouts

4. **Export data**
   - Download participant responses
   - Export game logs and analytics
   - Generate research datasets

### Participant Flow

1. **Consent & Information**: Study overview and consent
2. **Comprehension Check**: Payment understanding verification
3. **Waiting Room**: Auto-assignment to crews
4. **Game Rounds**: 6 rounds (0=training, 1-5=scored)
5. **Debrief Survey**: Demographics and feedback
6. **Completion**: Results and Prolific redirect

## Configuration

### Game Parameters
All game parameters are configurable via Django admin:

```python
EXPERIMENT_CONFIG = {
    'PU_PER_ROUND': 4,
    'TRAVEL_COSTS': {'Alpha': 0, 'Beta': 1, 'Gamma': 2, 'Omega': 3},
    'PROBE_COST': 1,
    'ROBOT_COST': 1,
    'MINE_SHALLOW_COST': 1,
    'MINE_DEEP_COST': 2,
    'BRIEFING_HIGH_PRESSURE': 90,
    'BRIEFING_LOW_PRESSURE': 180,
    'ACTION_STAGE_TIME': 15,
    'RESULT_STAGE_TIME': 15,
}
```

### Probability Matrix
Configure mining success rates:

```python
'DEFAULT_PROBABILITY_MATRIX': {
    'shallow': {
        'none': 0.15,
        'probe_only': 0.35,
        'robot_only': 0.30,
        'probe_plus_robot': 0.55,
    },
    'deep': {
        'none': 0.30,
        'robot_only': 0.50,
        'probe_only': 0.55,
        'probe_plus_robot': 0.80,
    }
}
```

## Development

### Project Structure
```
spaceship_coordination/
├── models.py          # Database models
├── views.py           # HTTP views and API endpoints
├── consumers.py       # WebSocket consumers
├── game_logic.py      # Core game engine
├── ai_captain.py      # AI captain system
├── admin.py           # Django admin configuration
├── migrations/        # Database migrations
└── templates/         # HTML templates
```

### Adding Features

1. **New game mechanics**: Extend `GameEngine` class
2. **Additional conditions**: Modify `ExperimentSession` model
3. **Custom analytics**: Add to `AnalyticsSnapshot` model
4. **UI enhancements**: Update templates and JavaScript

### Testing

```bash
# Run tests
python manage.py test spaceship_coordination

# Run with coverage
coverage run --source='.' manage.py test
coverage report
```

### Testing Enhanced Game Mechanics

Test the implementation of formal game mechanics:

```bash
# Test high complexity, low pressure
python manage.py test_game_mechanics --session-id "test_high_complexity" --complexity high --pressure low

# Test low complexity, high pressure  
python manage.py test_game_mechanics --session-id "test_low_complexity" --complexity low --pressure high

# Test with custom session ID
python manage.py test_game_mechanics --session-id "custom_test" --complexity high --pressure high
```

The test command validates:
- Round progression and stage transitions
- Action validation and constraints
- Mining outcomes and probability calculations
- Intel visibility based on complexity
- Communication rules enforcement
- Game state management

## Deployment

### Production Setup

1. **Environment variables**
   ```env
   DEBUG=False
   SECRET_KEY=secure-production-key
   ALLOWED_HOSTS=your-domain.com
   ```

2. **Static files**
   ```bash
   python manage.py collectstatic
   ```

3. **Database optimization**
   - Enable connection pooling
   - Configure appropriate indexes
   - Set up database backups

4. **WebSocket scaling**
   - Use Redis cluster for channel layers
   - Configure load balancer for WebSocket support
   - Monitor connection limits

### Docker Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN python manage.py collectstatic --noinput

EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "wsgi:application"]
```

## Data Export

### Research Data
The system logs comprehensive data for analysis:

- **Participant actions**: All game decisions and timing
- **Communication patterns**: Chat messages and coordination
- **Performance metrics**: Minerals gained, PU efficiency
- **Experimental conditions**: Condition assignments and randomization
- **System events**: Disconnections, timeouts, admin actions

### Export Formats
- **CSV**: Tabular data for statistical analysis
- **JSON**: Structured data for custom analysis
- **Database dumps**: Full dataset for advanced analysis

## Troubleshooting

### Common Issues

1. **WebSocket connections failing**
   - Check Redis is running
   - Verify channel layer configuration
   - Check firewall settings

2. **Database connection errors**
   - Verify PostgreSQL is running
   - Check database credentials
   - Ensure database exists

3. **Game state synchronization**
   - Check WebSocket consumer logs
   - Verify game engine state updates
   - Monitor database transaction logs

### Logs
- **Application logs**: `logs/spaceship_coordination.log`
- **Django logs**: Console output during development
- **WebSocket logs**: Channel layer debugging

## Contributing

1. Fork the repository
2. Create feature branch
3. Implement changes with tests
4. Submit pull request

## License

This project is licensed under the MIT License - see LICENSE file for details.

## Support

For technical support or research questions:
- Create an issue in the repository
- Contact the development team
- Refer to oTree documentation

## Acknowledgments

- Built with [oTree](https://otree.org/) framework
- WebSocket support via [Django Channels](https://channels.readthedocs.io/)
- AI integration using [AutoGen](https://microsoft.github.io/autogen/)
- Database design inspired by experimental economics best practices
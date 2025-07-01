# TransDock Frontend

This directory will contain the web-based user interface for TransDock.

## Planned Features

- **Dashboard**: Overview of migration status and system health
- **Migration Wizard**: Step-by-step guided migration process
- **Stack Manager**: Browse and analyze Docker Compose stacks
- **Real-time Progress**: Live migration progress tracking
- **History**: View past migrations and their status
- **Settings**: Configure SSH keys, default paths, and preferences

## Technology Stack (Planned)

- **Framework**: React 18+ with TypeScript
- **Styling**: Tailwind CSS
- **State Management**: Zustand or Redux Toolkit
- **API Client**: Axios with react-query
- **Charts**: Chart.js or Recharts for progress visualization
- **Notifications**: Toast notifications for status updates

## Development

The frontend is not yet implemented. To start development:

1. Initialize the frontend project:
   ```bash
   cd frontend
   npx create-react-app . --template typescript
   # or
   npm create vite@latest . -- --template react-ts
   ```

2. Install additional dependencies:
   ```bash
   npm install axios @tanstack/react-query tailwindcss
   ```

3. Configure API base URL to connect to the backend at `http://localhost:8000`

## API Integration

The frontend will connect to the TransDock backend API endpoints:

- `GET /system/info` - System information
- `GET /compose/stacks` - List available stacks
- `POST /migrations` - Start a migration
- `GET /migrations/{id}` - Get migration status
- `GET /migrations` - List all migrations

See the backend API documentation at `http://localhost:8000/docs` when the backend is running. 
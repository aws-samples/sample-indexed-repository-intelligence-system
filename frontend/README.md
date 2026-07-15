<!-- Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved. -->
<!-- SPDX-License-Identifier: MIT-0 -->

# IRIS React Frontend

A React-based chat interface for the IRIS system, built with AWS Cloudscape Design components for a professional appearance and optimal user experience.

## Overview

This React application provides a clean, responsive chat interface that connects to the IRIS backend for real-time code analysis and conversation. It's designed to be lightweight, fast, and user-friendly.

## Features

- **Real-time Chat Interface**: Interactive chat with streaming responses
- **AWS Cloudscape Design**: Professional UI components from AWS Design System
- **Conversation History**: Automatic saving and loading of chat sessions
- **Responsive Design**: Works on desktop and mobile devices
- **WebSocket Support**: Real-time communication with backend
- **Error Handling**: Graceful fallbacks and error messages
- **Configuration Management**: Dynamic configuration loading from backend

## Architecture

### Key Components

- **`src/App.jsx`**: Main application component and routing
- **`src/components/Chat.jsx`**: Core chat interface with message handling
- **`src/config/appConfig.js`**: Configuration and API service layer
- **`src/components/Chat.css`**: Custom styling for chat components

### Component Hierarchy

```
App.jsx
└── Chat.jsx
    ├── Message components (built-in Cloudscape)
    ├── Input components (built-in Cloudscape)
    └── History management
```

## Development

### Prerequisites

- Node.js 16+ and npm
- IRIS backend running (for full functionality)

### Setup

```bash
cd frontend/
npm install
```

### Development Server

```bash
npm start
```

Runs the app in development mode at `http://localhost:3000/`

### Production Build

```bash
npm run build
```

Builds the app for production to the `dist/` folder.

### Environment Configuration

#### Local Development

Edit `.env.development`:

```env
VITE_APP_NAME="IRIS"
VITE_BACKEND_URL="http://localhost:8000"
```

#### Docker Development

Edit `runtime-config-dev.js`:

```javascript
window.RUNTIME_CONFIG = {
  appName: "IRIS",
  backendUrl: "http://localhost:8000",
};
```

#### Cloud Deployment

Edit `runtime-config-cloud.js`:

```javascript
window.RUNTIME_CONFIG = {
  appName: "IRIS",
  backendUrl: "/api", // Same-origin path; app calls the AgentCore Runtime endpoint directly
};
```

## Backend Integration

### Expected API Endpoints

The React app expects the following backend endpoints:

- **`GET /api/config`** - Application configuration
- **`POST /api/query`** - Send chat messages (supports streaming)
- **`GET /api/conversation-history`** - Retrieve chat history
- **`POST /api/conversation-history`** - Save chat history
- **`DELETE /api/conversation-history`** - Clear chat history

### WebSocket Communication

For real-time features, the app can connect to WebSocket endpoints:

- **`ws://localhost:8000/ws`** - Local development WebSocket
- **`wss://your-domain.com/ws`** - Production WebSocket

### Message Format

**Outgoing Messages:**

```javascript
{
  type: "chat",
  message: "User's question here"
}
```

**Incoming Messages:**

```javascript
{
  type: "stream_chunk",
  data: {
    content: "Partial response...",
    full_content: "Complete response so far..."
  }
}
```

## Customization

### Branding

To customize the application name and branding:

1. **Development**: Update `VITE_APP_NAME` in `.env.development`
2. **Docker**: Update `appName` in `runtime-config-dev.js`
3. **Production**: Update `appName` in `runtime-config-cloud.js`

### Styling

The app uses AWS Cloudscape Design System with custom CSS in `Chat.css`. To modify styling:

1. **Cloudscape Theme**: Modify theme settings in `App.jsx`
2. **Custom Styles**: Edit `src/components/Chat.css`
3. **Component Props**: Adjust Cloudscape component properties

### Adding Features

To add new features:

1. **New Components**: Create in `src/components/`
2. **API Calls**: Add to `src/config/appConfig.js`
3. **Routing**: Update `src/App.jsx` if needed
4. **State Management**: Use React hooks or add state management library

## Docker Support

### Development Container

The app includes a Dockerfile for containerized development:

```bash
# Build container
docker build -t iris-frontend .

# Run container
docker run -p 3000:3000 iris-frontend
```

### Docker Compose Integration

When using with the full stack via `scripts/docker-compose.yml`:

```bash
# Start full stack
docker-compose up

# Frontend only
docker-compose up react-frontend
```

## Troubleshooting

### Common Issues

1. **Backend Connection Failed**
   - Verify backend is running on expected port
   - Check CORS configuration in backend
   - Verify API endpoint URLs in configuration

2. **Build Failures**
   - Clear node_modules: `rm -rf node_modules && npm install`
   - Clear npm cache: `npm cache clean --force`
   - Check Node.js version compatibility

3. **WebSocket Connection Issues**
   - Verify WebSocket URL in configuration
   - Check firewall/proxy settings
   - Ensure backend WebSocket server is running

4. **Styling Issues**
   - Clear browser cache
   - Check Cloudscape version compatibility
   - Verify CSS import paths

### Development Tips

- **Hot Reload**: Changes to React components auto-reload in development
- **Console Logs**: Check browser developer tools for error messages
- **Network Tab**: Monitor API calls and responses in browser dev tools
- **React DevTools**: Install React Developer Tools browser extension for debugging

## Dependencies

### Core Dependencies

- **React 18+**: Core framework
- **@cloudscape-design/components**: AWS UI component library
- **@cloudscape-design/global-styles**: AWS design system styles

### Development Dependencies

- **Vite**: Build tool and development server
- **@vitejs/plugin-react**: React support for Vite
- **ESLint**: Code linting
- **Prettier**: Code formatting

## Contributing

When contributing to the React frontend:

1. **Code Style**: Follow existing patterns and use Prettier formatting
2. **Components**: Use Cloudscape components when possible
3. **State Management**: Keep state management simple with React hooks
4. **Testing**: Add tests for new components (testing framework TBD)
5. **Documentation**: Update this README for significant changes

## Differences from CLI Version

This React frontend focuses on providing a web-based chat interface, while the CLI version (`iris` commands) provides:

- Interactive terminal-based chat
- Streamlit UI option
- Direct codebase analysis commands

The React app assumes backend handles codebase analysis and provides a chat experience for end users.

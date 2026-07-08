// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import React, { useState, useEffect, lazy, Suspense } from "react";
import { AlertTriangle, XCircle, X } from "lucide-react";
import Chat from "./components/Chat.jsx";
import Header from "./components/Header.jsx";
import MainLayout from "./components/MainLayout.jsx";
import CodebaseDrawer from "./components/CodebaseDrawer.jsx";
import { irisService } from "./services/irisService";
import { getAppConfig } from "./config/appConfig.js";
import { Amplify } from "aws-amplify";
import "@aws-amplify/ui-react/styles.css";

// Lazy load to avoid early initialization
const AuthenticatorWrapper = lazy(() =>
  import("@aws-amplify/ui-react").then((module) => ({
    default: ({ children }) => (
      <module.Authenticator
        hideSignUp={true}
        signUpAttributes={[]}
        loginMechanisms={["username"]}
        components={{
          Header() {
            const { appName } = getAppConfig();
            return (
              <div style={{ textAlign: "center", padding: "1rem" }}>
                <h2>Sign In</h2>
                <p>Sign in to {appName}</p>
              </div>
            );
          },
          SignIn: {
            FormFields() {
              return (
                <>
                  <module.Authenticator.SignIn.FormFields />
                </>
              );
            },
          },
        }}
        formFields={{
          signIn: {
            username: {
              label: "Username/Email",
              placeholder: "Enter your Username/Email",
              isRequired: true,
            },
          },
        }}
      >
        {children}
      </module.Authenticator>
    ),
  })),
);

/**
 * Loading spinner component
 */
function LoadingSpinner({ message = "Loading..." }) {
  return (
    <div className="flex flex-col items-center justify-center h-screen bg-gray-50">
      <div className="w-8 h-8 border-4 border-purple-200 border-t-purple-600 rounded-full animate-spin mb-4" />
      <p className="text-gray-600">{message}</p>
    </div>
  );
}

/**
 * Error display component
 */
function ErrorDisplay({ message, onRetry }) {
  return (
    <div className="flex flex-col items-center justify-center h-screen bg-gray-50 px-4">
      <div className="bg-red-50 border border-red-200 rounded-lg p-6 max-w-md text-center">
        <AlertTriangle className="w-12 h-12 text-red-500 mx-auto mb-4" />
        <h2 className="text-lg font-semibold text-red-800 mb-2">
          Configuration Error
        </h2>
        <p className="text-red-600 mb-4">{message}</p>
        {onRetry && (
          <button
            onClick={onRetry}
            className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
          >
            Retry
          </button>
        )}
      </div>
    </div>
  );
}

/**
 * Dismissible error alert component
 */
function ErrorAlert({ message, onDismiss }) {
  if (!message) return null;

  return (
    <div className="bg-red-50 border border-red-200 rounded-lg p-4 mx-4 mt-4 flex items-start gap-3">
      <XCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
      <p className="flex-1 text-sm text-red-700">{message}</p>
      <button
        onClick={onDismiss}
        className="text-red-500 hover:text-red-700 transition-colors"
        aria-label="Dismiss error"
      >
        <X className="w-5 h-5" />
      </button>
    </div>
  );
}

/**
 * AppContent component - Main application content with header, layout, and chat
 */
function AppContent({ signOut, user, showUserMenu = false }) {
  const [config, setConfig] = useState(null);
  const [codebaseInfo, setCodebaseInfo] = useState(null);
  const [treeStructure, setTreeStructure] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isReconnecting, setIsReconnecting] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(true);
  const [prefilledInput, setPrefilledInput] = useState("");
  const { appName } = getAppConfig();

  // Load configuration and codebase info from backend
  useEffect(() => {
    const loadData = async () => {
      try {
        setIsLoading(true);

        const [backendConfig, codebaseData] = await Promise.all([
          irisService.loadConfig(),
          irisService.getCodebaseInfo(),
        ]);

        setConfig(backendConfig);
        setCodebaseInfo(codebaseData);
        if (codebaseData && codebaseData.tree_structure) {
          setTreeStructure(codebaseData.tree_structure);
        } else {
          console.log(
            "No tree structure available from backend, drawer will be hidden",
          );
          setTreeStructure(null);
        }
      } catch (err) {
        console.error("Error loading data:", err);
        setError("Failed to load configuration from backend");
      } finally {
        setIsLoading(false);
      }
    };

    loadData();
  }, []);

  const handleRefreshContext = async () => {
    if (!config) return;

    try {
      setError(null);
      await irisService.generateContext(
        config.codebase_dir,
        config.output_dir,
      );
    } catch (err) {
      console.error("Error refreshing context:", err);
      setError("Failed to refresh context");
    }
  };

  const handleConnectionChange = (connected) => {
    setIsConnected(connected);
    if (connected) {
      setIsReconnecting(false);
    }
  };

  const handleReconnect = async () => {
    try {
      setIsReconnecting(true);
      setError(null);
      await irisService.reconnect();
      setIsConnected(true);
    } catch (err) {
      console.error("Reconnection failed:", err);
      setError("Failed to reconnect. Please try again.");
    } finally {
      setIsReconnecting(false);
    }
  };

  const handleDrawerToggle = () => {
    setDrawerOpen((prev) => !prev);
  };

  const handleFileClick = (filePath) => {
    // Set the prefilled input with a prompt about the file
    setPrefilledInput(`Tell me about ${filePath}`);
  };

  const handleInputUsed = () => {
    // Clear the prefilled input after it's been used
    setPrefilledInput("");
  };

  if (isLoading) {
    return <LoadingSpinner message="Loading configuration..." />;
  }

  if (error && !config) {
    return (
      <ErrorDisplay message={error} onRetry={() => window.location.reload()} />
    );
  }

  const hasDrawer = !!treeStructure;

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      <Header
        appName={appName}
        isConnected={isConnected}
        user={user}
        onSignOut={signOut}
        showUserMenu={showUserMenu}
        onReconnect={handleReconnect}
        isReconnecting={isReconnecting}
      />

      <ErrorAlert message={error} onDismiss={() => setError(null)} />

      <div className="flex-1 overflow-hidden">
        <MainLayout
          drawerOpen={drawerOpen}
          onDrawerToggle={handleDrawerToggle}
          hasDrawer={hasDrawer}
          drawer={
            hasDrawer
              ? ({ isOpen, onToggle }) => (
                  <CodebaseDrawer
                    isOpen={isOpen}
                    onToggle={onToggle}
                    codebaseInfo={codebaseInfo}
                    treeStructure={treeStructure}
                    onFileClick={handleFileClick}
                  />
                )
              : null
          }
        >
          <Chat
            config={config}
            onRefreshContext={handleRefreshContext}
            onConnectionChange={handleConnectionChange}
            prefilledInput={prefilledInput}
            onPrefilledInputUsed={handleInputUsed}
          />
        </MainLayout>
      </div>
    </div>
  );
}

function App() {
  const [isAmplifyConfigured, setIsAmplifyConfigured] = useState(false);

  // Configure Amplify dynamically when component mounts
  useEffect(() => {
    const config = getAppConfig();

    if (
      config.authEnabled &&
      config.cognito.userPoolId &&
      config.cognito.userPoolClientId
    ) {
      Amplify.configure({
        Auth: {
          Cognito: {
            userPoolId: config.cognito.userPoolId,
            userPoolClientId: config.cognito.userPoolClientId,
            loginWith: {
              username: true,
              email: true,
            },
          },
        },
      });
    }

    setIsAmplifyConfigured(true);
  }, []);

  const config = getAppConfig();

  // Wait for Amplify to be configured
  if (!isAmplifyConfigured) {
    return <LoadingSpinner message="Initializing authentication..." />;
  }

  // If auth is disabled, bypass authentication
  if (!config.authEnabled) {
    const mockUser = {
      signInDetails: { loginId: "Local User" },
    };

    return (
      <AppContent
        signOut={() => console.log("Sign out not available in local mode")}
        user={mockUser}
        showUserMenu={false}
      />
    );
  }

  // Otherwise, use Cognito authentication with lazy loading
  return (
    <Suspense fallback={<LoadingSpinner message="Loading authentication..." />}>
      <AuthenticatorWrapper>
        {({ signOut, user }) => (
          <AppContent signOut={signOut} user={user} showUserMenu={true} />
        )}
      </AuthenticatorWrapper>
    </Suspense>
  );
}

export default App;

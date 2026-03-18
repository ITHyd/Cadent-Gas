import { createContext, useContext, useState, useEffect, useCallback } from 'react';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

const AuthContext = createContext(null);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem('access_token'));
  const [isLoading, setIsLoading] = useState(true);

  const clearAuth = useCallback(() => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    setToken(null);
    setUser(null);
  }, []);

  const attemptRefresh = useCallback(async () => {
    const stored = localStorage.getItem('refresh_token');
    if (!stored) return false;

    try {
      const res = await fetch(
        `${API_BASE_URL}/api/v1/auth/refresh`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: stored }),
        },
      );
      if (!res.ok) return false;

      const data = await res.json();
      localStorage.setItem('access_token', data.access_token);
      if (data.refresh_token) localStorage.setItem('refresh_token', data.refresh_token);
      setToken(data.access_token);

      const meRes = await fetch(`${API_BASE_URL}/api/v1/auth/me`, {
        headers: { Authorization: `Bearer ${data.access_token}` },
      });
      if (meRes.ok) {
        setUser(await meRes.json());
        return true;
      }
    } catch {
      // refresh failed silently — user will be logged out
    }
    return false;
  }, []);

  // Validate stored token on mount
  useEffect(() => {
    const validate = async () => {
      const stored = localStorage.getItem('access_token');
      if (!stored) {
        setIsLoading(false);
        return;
      }

      try {
        const res = await fetch(`${API_BASE_URL}/api/v1/auth/me`, {
          headers: { Authorization: `Bearer ${stored}` },
        });

        if (res.ok) {
          setUser(await res.json());
          setToken(stored);
        } else {
          const refreshed = await attemptRefresh();
          if (!refreshed) clearAuth();
        }
      } catch {
        clearAuth();
      } finally {
        setIsLoading(false);
      }
    };
    validate();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const login = useCallback((tokenData) => {
    localStorage.setItem('access_token', tokenData.access_token);
    localStorage.setItem('refresh_token', tokenData.refresh_token);
    setToken(tokenData.access_token);
    setUser(tokenData.user);
  }, []);

  const logout = useCallback(() => {
    clearAuth();
  }, [clearAuth]);

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isAuthenticated: !!user && !!token,
        isLoading,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

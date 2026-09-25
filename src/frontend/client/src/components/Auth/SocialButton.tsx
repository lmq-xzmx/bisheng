import React, { useState } from 'react';
import { _get } from '~/api/request';

type OAuthAuthorizeResponse = {
  authorization_url: string;
};

const SocialButton = ({
  id,
  enabled,
  serverDomain,
  oauthPath,
  Icon,
  label,
}: {
  id: string;
  enabled: boolean;
  serverDomain: string;
  oauthPath: string;
  Icon: React.ComponentType | (() => React.ReactNode);
  label: string;
}) => {
  const [isLoading, setIsLoading] = useState(false);

  if (!enabled) {
    return null;
  }

  const handleClick = async (e: React.MouseEvent) => {
    e.preventDefault();
    setIsLoading(true);

    try {
      // Generate a random state for CSRF protection
      const state = Math.random().toString(36).substring(2, 15);

      // Call our backend to get the authorization URL
      const response = await _get<OAuthAuthorizeResponse>(
        `/api/v1/oauth/${oauthPath}/authorize`,
        {
          params: {
            state,
            tenant_id: 1, // TODO: get from context
          },
        }
      );

      // Redirect to the OAuth provider
      window.location.href = response.authorization_url;
    } catch (error) {
      console.error('Failed to get authorization URL:', error);
      setIsLoading(false);
    }
  };

  return (
    <div className="mt-2 flex gap-x-2">
      <a
        aria-label={`${label}`}
        className="flex w-full items-center space-x-3 rounded-2xl border border-border-light bg-surface-primary px-5 py-3 text-text-primary transition-colors duration-200 hover:bg-surface-tertiary"
        href="#"
        onClick={handleClick}
        data-testid={id}
      >
        {typeof Icon === 'function' ? <Icon /> : <Icon />}
        <p>{isLoading ? 'Redirecting...' : label}</p>
      </a>
    </div>
  );
};

export default SocialButton;

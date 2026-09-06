import { useOAuthProviders } from '~/hooks/queries/auth/oauth';

import SocialButton from './SocialButton';

import { useLocalize } from '~/hooks';

import { TStartupConfig } from '~/types/chat';
import { GoogleIcon, FacebookIcon, OpenIDIcon, GithubIcon, DiscordIcon, AppleIcon } from '~/components';

function SocialLoginRender({
  startupConfig,
}: {
  startupConfig: TStartupConfig | null | undefined;
}) {
  const localize = useLocalize();

  // Try to fetch providers from API (new config-driven approach)
  // Use tenant_id=1 as default, or extract from current user context if available
  const { data: providersData, isSuccess } = useOAuthProviders(1);

  if (!startupConfig) {
    return null;
  }

  // If API returns providers, use them (config-driven dynamic rendering)
  if (isSuccess && providersData?.providers?.length) {
    return (
      startupConfig.socialLoginEnabled && (
        <>
          {startupConfig.emailLoginEnabled && (
            <>
              <div className="relative mt-6 flex w-full items-center justify-center border border-t border-gray-300 uppercase dark:border-gray-600">
                <div className="absolute bg-white px-3 text-xs text-black dark:bg-gray-900 dark:text-white">
                  Or
                </div>
              </div>
              <div className="mt-8" />
            </>
          )}
          <div className="mt-2">
            {providersData.providers
              .filter((p) => p.enabled)
              .map((provider) => (
                <SocialButton
                  key={provider.id}
                  enabled={true}
                  serverDomain={startupConfig.serverDomain}
                  oauthPath={provider.id}
                  Icon={() => getProviderIcon(provider.id)}
                  label={provider.name}
                  id={provider.id}
                />
              ))}
          </div>
        </>
      )
    );
  }

  // Fallback to old hardcoded behavior (backward compatibility)
  const providerComponents = {
    discord: startupConfig.discordLoginEnabled && (
      <SocialButton
        key="discord"
        enabled={startupConfig.discordLoginEnabled}
        serverDomain={startupConfig.serverDomain}
        oauthPath="discord"
        Icon={DiscordIcon}
        label={localize('com_auth_discord_login')}
        id="discord"
      />
    ),
    facebook: startupConfig.facebookLoginEnabled && (
      <SocialButton
        key="facebook"
        enabled={startupConfig.facebookLoginEnabled}
        serverDomain={startupConfig.serverDomain}
        oauthPath="facebook"
        Icon={FacebookIcon}
        label={localize('com_auth_facebook_login')}
        id="facebook"
      />
    ),
    github: startupConfig.githubLoginEnabled && (
      <SocialButton
        key="github"
        enabled={startupConfig.githubLoginEnabled}
        serverDomain={startupConfig.serverDomain}
        oauthPath="github"
        Icon={GithubIcon}
        label={localize('com_auth_github_login')}
        id="github"
      />
    ),
    google: startupConfig.googleLoginEnabled && (
      <SocialButton
        key="google"
        enabled={startupConfig.googleLoginEnabled}
        serverDomain={startupConfig.serverDomain}
        oauthPath="google"
        Icon={GoogleIcon}
        label={localize('com_auth_google_login')}
        id="google"
      />
    ),
    apple: startupConfig.appleLoginEnabled && (
      <SocialButton
        key="apple"
        enabled={startupConfig.appleLoginEnabled}
        serverDomain={startupConfig.serverDomain}
        oauthPath="apple"
        Icon={AppleIcon}
        label={localize('com_auth_apple_login')}
        id="apple"
      />
    ),
    openid: startupConfig.openidLoginEnabled && (
      <SocialButton
        key="openid"
        enabled={startupConfig.openidLoginEnabled}
        serverDomain={startupConfig.serverDomain}
        oauthPath="openid"
        Icon={() =>
          startupConfig.openidImageUrl ? (
            <img src={startupConfig.openidImageUrl} alt="OpenID Logo" className="h-5 w-5" />
          ) : (
            <OpenIDIcon />
          )
        }
        label={startupConfig.openidLabel}
        id="openid"
      />
    ),
  };

  return (
    startupConfig.socialLoginEnabled && (
      <>
        {startupConfig.emailLoginEnabled && (
          <>
            <div className="relative mt-6 flex w-full items-center justify-center border border-t border-gray-300 uppercase dark:border-gray-600">
              <div className="absolute bg-white px-3 text-xs text-black dark:bg-gray-900 dark:text-white">
                Or
              </div>
            </div>
            <div className="mt-8" />
          </>
        )}
        <div className="mt-2">
          {startupConfig.socialLogins?.map((provider) => providerComponents[provider] || null)}
        </div>
      </>
    )
  );
}

// Helper function to get icon component by provider ID
function getProviderIcon(providerId: string) {
  const icons: Record<string, React.ReactNode> = {
    google: <GoogleIcon />,
    github: <GithubIcon />,
    facebook: <FacebookIcon />,
    discord: <DiscordIcon />,
    apple: <AppleIcon />,
    wechat: <div className="text-2xl">💬</div>, // Placeholder - should use actual WeChat icon
    alipay: <div className="text-2xl">💳</div>, // Placeholder - should use actual Alipay icon
  };
  return icons[providerId] || <div className="text-2xl">{providerId[0]?.toUpperCase()}</div>;
}

export default SocialLoginRender;

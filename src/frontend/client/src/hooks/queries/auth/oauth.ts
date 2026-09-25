import { useQuery } from '@tanstack/react-query';
import { _get } from '~/api/request';

export type OAuthProvider = {
  id: string;
  name: string;
  icon: string;
  enabled: boolean;
};

type OAuthProvidersResponse = {
  providers: OAuthProvider[];
};

export function useOAuthProviders(tenantId: number | undefined) {
  return useQuery({
    queryKey: ['oauth-providers', tenantId],
    queryFn: () => _get<OAuthProvidersResponse>('/api/v1/oauth/providers', { params: { tenant_id: tenantId } }),
    enabled: !!tenantId,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

import axios from "../request";

/**
 * LDAP login via user_sync module
 */
export async function ldapLoginApi(username: string, password: string, tenantId: number = 1) {
    return await axios.post('/api/v1/user/ldap/login', {
        username,
        password,
        tenant_id: tenantId,
    });
}

/**
 * OAuth providers list for dynamic rendering
 */
export async function getOAuthProvidersApi(tenantId: number = 1) {
    return await axios.get('/api/v1/oauth/providers', {
        params: { tenant_id: tenantId },
    });
}

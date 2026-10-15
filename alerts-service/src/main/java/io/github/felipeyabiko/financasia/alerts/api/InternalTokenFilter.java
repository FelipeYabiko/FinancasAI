package io.github.felipeyabiko.financasia.alerts.api;

import io.github.felipeyabiko.financasia.alerts.config.AlertsProperties;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * Service-to-service authentication: when {@code alerts.internal-token} is set, every /api call
 * must carry it in {@code X-Internal-Token}. The service is meant to sit on an internal network
 * behind the main app, which is the only caller.
 */
@Component
public class InternalTokenFilter extends OncePerRequestFilter {

    static final String HEADER = "X-Internal-Token";
    private final byte[] token;

    public InternalTokenFilter(AlertsProperties properties) {
        this.token = properties.internalToken().getBytes(StandardCharsets.UTF_8);
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return token.length == 0 || !request.getRequestURI().startsWith("/api/");
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String sent = request.getHeader(HEADER);
        // constant-time comparison
        if (sent == null || !MessageDigest.isEqual(token, sent.getBytes(StandardCharsets.UTF_8))) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED, "invalid internal token");
            return;
        }
        chain.doFilter(request, response);
    }
}

package io.github.felipeyabiko.financasia.alerts.api;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import io.github.felipeyabiko.financasia.alerts.alert.Alert;
import io.github.felipeyabiko.financasia.alerts.alert.AlertService;
import io.github.felipeyabiko.financasia.alerts.alert.Severity;
import io.github.felipeyabiko.financasia.alerts.config.AlertsProperties;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Import;
import org.springframework.data.domain.PageImpl;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(AlertController.class)
@Import(AlertControllerTest.PropertiesConfig.class)
@TestPropertySource(properties = "alerts.internal-token=s3cret")
class AlertControllerTest {

    /** The MVC slice doesn't scan @ConfigurationProperties; the token filter needs them. */
    @TestConfiguration
    @EnableConfigurationProperties(AlertsProperties.class)
    static class PropertiesConfig {}

    @Autowired
    MockMvc mvc;

    @MockitoBean
    AlertService service;

    private final Alert alert = new Alert("e1", 7L, "budget", Severity.DANGER, "Orçamento estourado",
            "Delivery: R$ 430,00 de R$ 400,00", Map.of("percentual", "107%"), false, Instant.parse("2026-10-15T10:00:00Z"));

    @Test
    void listsAlerts() throws Exception {
        when(service.list(eq(true), any())).thenReturn(new PageImpl<>(List.of(alert)));
        mvc.perform(get("/api/alerts?unreadOnly=true").header("X-Internal-Token", "s3cret"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[0].rule").value("budget"))
                .andExpect(jsonPath("$.items[0].severity").value("DANGER"))
                .andExpect(jsonPath("$.total").value(1));
    }

    @Test
    void rejectsCallsWithoutTheInternalToken() throws Exception {
        mvc.perform(get("/api/alerts")).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/alerts").header("X-Internal-Token", "wrong")).andExpect(status().isUnauthorized());
    }

    @Test
    void markReadReturns404ForUnknownAlert() throws Exception {
        when(service.markRead("nope")).thenThrow(new NoSuchElementException("alert nope not found"));
        mvc.perform(patch("/api/alerts/nope/read").header("X-Internal-Token", "s3cret"))
                .andExpect(status().isNotFound());
    }

    @Test
    void validatesPageSize() throws Exception {
        mvc.perform(get("/api/alerts?size=500").header("X-Internal-Token", "s3cret")).andExpect(status().isBadRequest());
    }
}

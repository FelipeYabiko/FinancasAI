package io.github.felipeyabiko.financasia.alerts.api;

import io.github.felipeyabiko.financasia.alerts.alert.AlertService;
import io.github.felipeyabiko.financasia.alerts.alert.Severity;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import org.springframework.data.domain.PageRequest;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/alerts")
@Validated
public class AlertController {

    private final AlertService service;

    public AlertController(AlertService service) {
        this.service = service;
    }

    @GetMapping
    public AlertPage list(
            @RequestParam(defaultValue = "false") boolean unreadOnly,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size) {
        var result = service.list(unreadOnly, PageRequest.of(page, size));
        return new AlertPage(result.map(AlertDto::from).getContent(), result.getTotalElements(), page, size);
    }

    @PatchMapping("/{id}/read")
    public AlertDto markRead(@PathVariable String id) {
        return AlertDto.from(service.markRead(id));
    }

    @GetMapping("/summary")
    public Map<Severity, Long> unreadSummary() {
        Map<Severity, Long> out = new EnumMap<>(Severity.class);
        for (Severity s : Severity.values()) {
            out.put(s, service.unreadCount(s));
        }
        return out;
    }

    public record AlertPage(List<AlertDto> items, long total, int page, int size) {}
}

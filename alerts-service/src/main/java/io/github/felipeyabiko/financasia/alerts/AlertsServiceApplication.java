package io.github.felipeyabiko.financasia.alerts;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class AlertsServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(AlertsServiceApplication.class, args);
    }
}

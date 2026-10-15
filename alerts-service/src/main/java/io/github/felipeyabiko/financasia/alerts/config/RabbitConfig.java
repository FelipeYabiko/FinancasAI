package io.github.felipeyabiko.financasia.alerts.config;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Topology: the app publishes to the topic exchange; this service owns its queue. Messages that
 * keep failing (after the listener's retries) are dead-lettered to {@code <queue>.dlq} instead of
 * being lost or redelivered forever.
 */
@Configuration
public class RabbitConfig {

    @Bean
    TopicExchange eventsExchange(AlertsProperties props) {
        return new TopicExchange(props.exchange(), true, false);
    }

    @Bean
    TopicExchange deadLetterExchange(AlertsProperties props) {
        return new TopicExchange(props.exchange() + ".dlx", true, false);
    }

    @Bean
    Queue alertsQueue(AlertsProperties props) {
        return QueueBuilder.durable(props.queue())
                .deadLetterExchange(props.exchange() + ".dlx")
                .deadLetterRoutingKey(props.queue() + ".dlq")
                .build();
    }

    @Bean
    Queue deadLetterQueue(AlertsProperties props) {
        return QueueBuilder.durable(props.queue() + ".dlq").build();
    }

    @Bean
    Binding alertsBinding(Queue alertsQueue, TopicExchange eventsExchange, AlertsProperties props) {
        return BindingBuilder.bind(alertsQueue).to(eventsExchange).with(props.routingKey());
    }

    @Bean
    Binding deadLetterBinding(Queue deadLetterQueue, TopicExchange deadLetterExchange, AlertsProperties props) {
        return BindingBuilder.bind(deadLetterQueue).to(deadLetterExchange).with(props.queue() + ".dlq");
    }

    @Bean
    MessageConverter jsonMessageConverter(ObjectMapper objectMapper) {
        return new Jackson2JsonMessageConverter(objectMapper);
    }
}

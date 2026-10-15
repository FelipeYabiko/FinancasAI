package io.github.felipeyabiko.financasia.alerts.rules;

import java.text.NumberFormat;
import java.util.Locale;

/** Integer cents to "R$ 1.234,56" (no floating point involved in the value itself). */
public final class Money {

    private static final Locale PT_BR = Locale.forLanguageTag("pt-BR");

    private Money() {}

    public static String brl(long cents) {
        String sign = cents < 0 ? "-" : "";
        long abs = Math.abs(cents);
        String integer = NumberFormat.getIntegerInstance(PT_BR).format(abs / 100);
        return "%sR$ %s,%02d".formatted(sign, integer, abs % 100);
    }
}

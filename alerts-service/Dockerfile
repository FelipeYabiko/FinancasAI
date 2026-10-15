# syntax=docker/dockerfile:1
# --- build stage: compile + package with the Maven wrapper (tests run in CI, not here) ---
FROM eclipse-temurin:21-jdk AS build
WORKDIR /src
COPY .mvn .mvn
COPY mvnw pom.xml ./
RUN ./mvnw -B -ntp dependency:go-offline
COPY src src
RUN ./mvnw -B -ntp -DskipTests package && cp target/alerts-service-*.jar /app.jar

# --- runtime stage: JRE only, non-root ---
FROM eclipse-temurin:21-jre
RUN useradd --system --uid 1001 alerts
USER alerts
COPY --from=build /app.jar /app/app.jar
EXPOSE 8081
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=75", "-jar", "/app/app.jar"]

package com.archisurance.claims.domain;

import lombok.Data;
import lombok.Builder;
import javax.persistence.*;
import java.time.LocalDateTime;
import java.math.BigDecimal;

/**
 * Domain model for the Claims business domain.
 * Maps to ArchiMate BusinessObjects: Claim, Customer Profile, Risk Score.
 */
public class ClaimsDomainModel {

    @Entity
    @Table(name = "claims")
    @Data
    public static class ClaimEntity {
        @Id
        private String claimId;
        private String customerId;
        private String policyId;
        private String type; // AUTO, HEALTH, PROPERTY, LIABILITY
        private BigDecimal amount;
        private String status; // REGISTERED, PENDING_ASSESSMENT, APPROVED, REJECTED
        private Double riskScore;
        private Boolean fraudSuspected;
        private LocalDateTime createdAt;
        private LocalDateTime assessedAt;
    }

    @Data
    public static class ClaimRequest {
        private String customerId;
        private String policyId;
        private String type;
        private BigDecimal amount;
        private String description;
    }

    @Data
    @Builder
    public static class ClaimResponse {
        private String claimId;
        private String status;
        private Double riskScore;
        private LocalDateTime createdAt;

        public static ClaimResponse from(ClaimRecord record) {
            return ClaimResponse.builder()
                .claimId(record.getClaimId())
                .status(record.getStatus())
                .riskScore(record.getRiskScore())
                .createdAt(record.getCreatedAt())
                .build();
        }
    }

    @Data
    @Builder
    public static class AssessmentResult {
        private String claimId;
        private RiskScore riskScore;
        private FraudScreenResult fraudResult;
        private String recommendation; // APPROVE, REVIEW, REJECT
    }
}

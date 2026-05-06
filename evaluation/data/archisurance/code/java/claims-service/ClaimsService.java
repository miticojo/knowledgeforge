package com.archisurance.claims.domain.service;

import org.springframework.stereotype.Service;
import com.archisurance.claims.domain.ClaimsDomainModel.*;
import com.archisurance.claims.port.out.ClaimsPersistencePort;
import com.archisurance.claims.port.out.RiskEnginePort;
import com.archisurance.claims.port.out.FraudDetectionPort;
import com.archisurance.claims.port.out.NotificationPort;

/**
 * Core business logic for the Claims Management Platform (ApplicationComponent).
 * Orchestrates Claims Registration and Claims Assessment processes.
 *
 * Serves: Claims Registration, Claims Assessment (BusinessProcess)
 * Accesses: Claim Record, Customer Profile (DataObject)
 * Triggers: Fraud Detection, Premium Calculation (BusinessProcess)
 */
@Service
public class ClaimsService {

    private final ClaimsPersistencePort persistencePort;
    private final RiskEnginePort riskEngine;
    private final FraudDetectionPort fraudDetection;
    private final NotificationPort notifications;

    public ClaimsService(ClaimsPersistencePort persistencePort,
                         RiskEnginePort riskEngine,
                         FraudDetectionPort fraudDetection,
                         NotificationPort notifications) {
        this.persistencePort = persistencePort;
        this.riskEngine = riskEngine;
        this.fraudDetection = fraudDetection;
        this.notifications = notifications;
    }

    public ClaimResponse registerClaim(ClaimRequest request) {
        // Validate customer identity via CRM System
        ClaimRecord record = ClaimRecord.create(request);
        persistencePort.save(record);

        // Trigger fraud screening via Fraud Detection Engine
        FraudScreenResult fraudResult = fraudDetection.screen(record);
        if (fraudResult.isSuspicious()) {
            notifications.notifyFraudTeam(record, fraudResult);
        }

        // Trigger risk evaluation via Risk Engine
        RiskScore riskScore = riskEngine.evaluate(record);
        record.setRiskScore(riskScore);
        persistencePort.update(record);

        return ClaimResponse.from(record);
    }

    public ClaimResponse getClaim(String claimId) {
        return ClaimResponse.from(persistencePort.findById(claimId));
    }

    public AssessmentResult assessClaim(String claimId) {
        ClaimRecord record = persistencePort.findById(claimId);
        // Claims Assessment uses Workflow Engine for step orchestration
        RiskScore score = riskEngine.evaluate(record);
        FraudScreenResult fraud = fraudDetection.screen(record);

        AssessmentResult result = AssessmentResult.builder()
            .claimId(claimId)
            .riskScore(score)
            .fraudResult(fraud)
            .recommendation(score.getValue() < 0.3 ? "APPROVE" : "REVIEW")
            .build();

        // Notify via Notification Service
        notifications.notifyClaimant(record, result);
        return result;
    }
}

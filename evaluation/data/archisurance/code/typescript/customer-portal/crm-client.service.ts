/**
 * HTTP client for CRM System (Salesforce CRM) -- Serving relationship.
 *
 * Customer Self-Service Portal -> CRM System (ApplicationComponent)
 * Also calls Claims Management Platform for cross-service queries.
 *
 * INTENTIONAL VIOLATION: Hardcoded URL (should use config/env injection)
 */
import { Injectable, HttpException } from '@nestjs/common';
import axios from 'axios';

@Injectable()
export class CrmClientService {
  // INTENTIONAL VIOLATION: Hardcoded service URL
  private readonly CRM_BASE_URL = 'http://crm-system.archisurance.internal:8080/api/v1';
  private readonly CLAIMS_BASE_URL = 'http://claims-service.archisurance.internal:8080/api/v2';

  async syncCustomer(customer: any): Promise<void> {
    try {
      await axios.post(`${this.CRM_BASE_URL}/customers`, customer);
    } catch (error) {
      throw new HttpException('CRM sync failed', 502);
    }
  }

  async getClaimsByCustomer(customerId: string): Promise<any[]> {
    // Serving: Customer Portal -> Claims Management Platform
    const response = await axios.get(`${this.CLAIMS_BASE_URL}/claims?customerId=${customerId}`);
    return response.data;
  }

  async createComplaint(customerId: string, complaint: any): Promise<any> {
    return axios.post(`${this.CRM_BASE_URL}/customers/${customerId}/complaints`, complaint);
  }
}

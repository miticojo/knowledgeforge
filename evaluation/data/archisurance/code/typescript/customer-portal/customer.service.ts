/**
 * Customer Self-Service Portal -- ApplicationComponent
 *
 * Serves: Customer Onboarding, Complaint Handling (BusinessProcess)
 * Accesses: Customer Record, Customer Profile (DataObject)
 * Depends on: CRM System (via CrmClientService), IAM (for auth)
 */
import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { CustomerEntity, CreateCustomerDto, CustomerResponseDto } from './customer.entity';
import { CrmClientService } from './crm-client.service';

@Injectable()
export class CustomerService {

  constructor(
    @InjectRepository(CustomerEntity)
    private readonly customerRepo: Repository<CustomerEntity>,
    private readonly crmClient: CrmClientService,
  ) {}

  async onboard(dto: CreateCustomerDto): Promise<CustomerResponseDto> {
    // Save to local PostgreSQL (DataObject: Customer Record)
    const entity = this.customerRepo.create(dto);
    const saved = await this.customerRepo.save(entity);

    // Sync to CRM System (Serving: Portal -> CRM System)
    await this.crmClient.syncCustomer(saved);

    return CustomerResponseDto.from(saved);
  }

  async findById(id: string): Promise<CustomerResponseDto> {
    const entity = await this.customerRepo.findOne({ where: { customerId: id } });
    if (!entity) throw new NotFoundException(`Customer ${id} not found`);
    return CustomerResponseDto.from(entity);
  }

  async getClaimsForCustomer(customerId: string) {
    // Cross-service: Customer Portal -> Claims Management Platform
    return this.crmClient.getClaimsByCustomer(customerId);
  }

  async fileComplaint(customerId: string, complaint: any) {
    // Complaint Handling -> Notification Service
    return this.crmClient.createComplaint(customerId, complaint);
  }
}

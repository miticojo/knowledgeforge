/**
 * Customer data model -- DataObject: Customer Record, Customer Profile
 *
 * Stored in PostgreSQL 15 (SystemSoftware).
 * Accessed by: Customer Self-Service Portal, CRM System (ApplicationComponent).
 */
import { Entity, PrimaryColumn, Column, CreateDateColumn } from 'typeorm';

@Entity('customers')
export class CustomerEntity {
  @PrimaryColumn()
  customerId: string;

  @Column()
  firstName: string;

  @Column()
  lastName: string;

  @Column()
  email: string;

  @Column({ nullable: true })
  phone: string;

  @Column({ type: 'date', nullable: true })
  dateOfBirth: Date;

  @Column({ default: 'ACTIVE' })
  status: string; // ACTIVE, SUSPENDED, CLOSED

  @Column({ default: 0 })
  npsScore: number;

  @CreateDateColumn()
  createdAt: Date;
}

export class CreateCustomerDto {
  firstName: string;
  lastName: string;
  email: string;
  phone?: string;
  dateOfBirth?: string;
}

export class CustomerResponseDto {
  customerId: string;
  firstName: string;
  lastName: string;
  email: string;
  status: string;
  createdAt: Date;

  static from(entity: CustomerEntity): CustomerResponseDto {
    return {
      customerId: entity.customerId,
      firstName: entity.firstName,
      lastName: entity.lastName,
      email: entity.email,
      status: entity.status,
      createdAt: entity.createdAt,
    };
  }
}
